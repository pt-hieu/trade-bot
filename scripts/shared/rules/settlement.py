"""T+2 settlement rules for VN stocks.

Single source of truth for when shares become sellable. Used at alert
registration time (morning scan) AND at evaluation time (alert_monitor).

VN market settles T+2 trading days — shares bought on trading day D are
credited by VSD at ~16:30 on D+2 and become sellable on that date. Any
EXIT/TRIM/STOP alert that fires before settlement is noise because the
user physically cannot execute the sell.

Pure deterministic Python: no LLM, no judgment — arithmetic on trading days
plus one DB read of OPEN trades.

Note: Only `status = 'OPEN'` contributes to settled shares. `PARTIAL` is
deliberately excluded — the enum exists but has zero writers, and the
`shares` column's semantics for partial rows are undefined. When a
scale-out feature ships, the same change must (a) define PARTIAL-row
`shares` semantics and (b) add PARTIAL to the query here.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from shared.database import fetch_all
from shared.market_calendar import is_trading_day

SETTLEMENT_TRADING_DAYS = 2


def trading_days_after(base: date, n: int) -> date:
    """Return the date `n` trading days after `base` (exclusive).

    `base` itself does not count. Walks forward one calendar day at a
    time, skipping weekends and holidays via `is_trading_day`.
    """
    if n <= 0:
        return base
    current = base
    remaining = n
    # Bound covers Tet (up to 9 consecutive non-trading days) plus slack
    # — never hit in practice for n ≤ 5.
    max_steps = 30 * n
    for _ in range(max_steps):
        current = current + timedelta(days=1)
        if is_trading_day(current):
            remaining -= 1
            if remaining == 0:
                return current
    msg = f"No {n} trading days found within {max_steps} days after {base}"
    raise ValueError(msg)


def settlement_date(trade_date: date) -> date:
    """Return the date on which shares bought on `trade_date` settle (T+2)."""
    return trading_days_after(trade_date, SETTLEMENT_TRADING_DAYS)


def trading_days_between(start: date, end: date) -> int:
    """Count trading days strictly after `start` up to and including `end`.

    Returns 0 when `end <= start`. Uses the same `is_trading_day` filter as
    `trading_days_after` so the weekday + holiday rules match.
    """
    if end <= start:
        return 0
    count = 0
    current = start
    while current < end:
        current = current + timedelta(days=1)
        if is_trading_day(current):
            count += 1
    return count


@dataclass(frozen=True)
class OpenTradesSnapshot:
    """Aggregated view of live OPEN trades for settlement decisions.

    Produced by one DB read. Consumers that need both settled shares and
    earliest entry dates (e.g. trailing-stop registration with two log
    branches) avoid a second scan of `trades_calculated`.
    """

    settled_by_ticker: dict[str, int]
    earliest_entry_by_ticker: dict[str, date]


async def load_open_trades_snapshot(as_of: date) -> OpenTradesSnapshot:
    """Return a one-shot snapshot of OPEN trades for `as_of`.

    `settled_by_ticker` sums `shares` across lots whose
    `settlement_date(entry_date) <= as_of`. Unsettled lots contribute 0.
    `earliest_entry_by_ticker` carries min(entry_date) per ticker across
    all OPEN lots, used to explain "unsettled" skip logs.

    VSD credits shares at ~16:30 on T+2 (post-close). We treat the full
    T+2 trading day as sellable — alert granularity (morning + 5-min
    polling) does not benefit from sub-day precision.
    """
    rows = await fetch_all(
        "SELECT ticker, entry_date, shares FROM trades_calculated WHERE status = 'OPEN'"
    )
    settled: dict[str, int] = {}
    earliest: dict[str, date] = {}
    for row in rows:
        ticker = row.get("ticker")
        entry_date = row.get("entry_date")
        shares = row.get("shares") or 0
        if not ticker or not entry_date:
            continue
        prior = earliest.get(ticker)
        if prior is None or entry_date < prior:
            earliest[ticker] = entry_date
        if shares <= 0:
            continue
        if settlement_date(entry_date) <= as_of:
            settled[ticker] = settled.get(ticker, 0) + int(shares)
    return OpenTradesSnapshot(settled_by_ticker=settled, earliest_entry_by_ticker=earliest)


async def get_settled_shares_by_ticker(as_of: date) -> dict[str, int]:
    """Thin wrapper — return only the settled-shares map."""
    snapshot = await load_open_trades_snapshot(as_of)
    return snapshot.settled_by_ticker


def is_sellable(ticker: str, settled: dict[str, int]) -> bool:
    """Return True iff `ticker` has at least one settled share."""
    return (settled.get(ticker) or 0) > 0
