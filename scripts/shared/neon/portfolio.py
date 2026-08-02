"""Portfolio, cash, goals, and sector allocation queries."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..database import get_db
from ._sync import make_sync
from ._types import GoalData, SwingTradeStats


@dataclass(frozen=True)
class HoldingsSnapshot:
    """Holdings rows plus the freshest ``updated_at`` across them.

    ``snapshot_at`` is the last write of any per-ticker ``current_price_vnd``;
    it is a row-mutation timestamp, NOT a market observation timestamp.
    Renderers must label this exactly as "Prices last written" — never
    "as of" — so operators are not gaslit on stale-data days (SWI-121).
    """

    holdings: list[dict]
    snapshot_at: datetime | None


async def get_portfolio_holdings() -> list[dict]:
    """Query portfolio holdings (one row per ticker+plan_type slice).

    Migration 314 enforces uniqueness on ``(ticker, plan_type)``. The previous
    dict-keyed-by-ticker return silently dropped the LONGTERM slice of any
    dual-listed ticker; callers that need dict access should use
    :func:`index_holdings_by_ticker_plan` or :func:`primary_swing_slice`.

    Callers that also need the freshest ``updated_at`` (for the MY HOLDINGS
    "Prices last written" header) should use
    :func:`get_portfolio_holdings_snapshot` instead.
    """
    snapshot = await get_portfolio_holdings_snapshot()
    return snapshot.holdings


async def get_portfolio_holdings_snapshot() -> HoldingsSnapshot:
    """Return :class:`HoldingsSnapshot` carrying holdings + freshest ``updated_at`` (SWI-121).

    ``snapshot_at`` collapses to ``None`` when every row has a NULL
    ``updated_at`` (defensive — column is NOT NULL today, but
    ``r.get("updated_at") or default`` keeps the helper aligned with
    CLAUDE.md's none-safe access rule).
    """
    db = await get_db()

    rows = await db.fetch_all("""
        SELECT ticker, shares, avg_cost_vnd, holding_type, current_price_vnd,
               plan_type, updated_at
        FROM portfolio_holdings
        WHERE shares > 0 AND holding_type != 'Cash'
        ORDER BY ticker, plan_type
    """)

    snapshot_at = max((r["updated_at"] for r in rows if r.get("updated_at")), default=None)

    cash = await db.fetch_val("""
        SELECT avg_cost_vnd
        FROM portfolio_holdings
        WHERE UPPER(ticker) = 'CASH' AND holding_type = 'Cash'
    """)
    cash_balance = float(cash) if cash is not None else 0

    total_holdings_value = 0.0
    slice_raw: list[dict[str, Any]] = []
    ticker_total_value: dict[str, float] = defaultdict(float)

    for row in rows:
        shares = row["shares"] or 0
        avg_cost_vnd = row["avg_cost_vnd"] or 0
        current_price_vnd = row["current_price_vnd"] or avg_cost_vnd
        market_value = float(shares * current_price_vnd) if current_price_vnd else 0.0
        total_holdings_value += market_value
        ticker_total_value[row["ticker"]] += market_value

        slice_raw.append(
            {
                "ticker": row["ticker"],
                "plan_type": (row["plan_type"] or "SWING"),
                "shares": shares,
                "avg_cost_vnd": avg_cost_vnd,
                "current_price_vnd": current_price_vnd,
                "holding_type": row["holding_type"],
                "market_value": market_value,
            }
        )

    total_portfolio = total_holdings_value + cash_balance

    holdings: list[dict] = []
    for data in slice_raw:
        ticker: str = data["ticker"]
        avg_cost_vnd = data["avg_cost_vnd"]
        current_price_vnd = data["current_price_vnd"]
        market_value = data["market_value"]

        avg_cost = int(avg_cost_vnd) if avg_cost_vnd else 0
        current_price = int(current_price_vnd) if current_price_vnd else None

        pct_from_entry = None
        if avg_cost_vnd and current_price_vnd:
            pct_from_entry = round((current_price_vnd - avg_cost_vnd) / avg_cost_vnd * 100, 1)

        slice_weight_pct = (
            round(market_value / total_portfolio * 100, 1) if total_portfolio > 0 else 0.0
        )
        ticker_weight_pct = (
            round(ticker_total_value[ticker] / total_portfolio * 100, 1)
            if total_portfolio > 0
            else 0.0
        )

        holdings.append(
            {
                "ticker": ticker,
                "plan_type": data["plan_type"],
                "shares": data["shares"],
                "avg_cost": avg_cost,
                "avg_cost_vnd": data["avg_cost_vnd"],
                "type": data["holding_type"] or "Stock",
                "current_price_vnd": current_price,
                "market_value": market_value,
                "slice_weight_pct": slice_weight_pct,
                "ticker_weight_pct": ticker_weight_pct,
                "pct_from_entry": pct_from_entry,
                "breakeven_stop": avg_cost,
            }
        )

    return HoldingsSnapshot(holdings=holdings, snapshot_at=snapshot_at)


def index_holdings_by_ticker_plan(
    holdings: list[dict],
) -> dict[tuple[str, str], dict]:
    """Index the list form by ``(ticker, plan_type)`` for O(1) slice lookup."""
    return {(slice_row["ticker"], slice_row["plan_type"]): slice_row for slice_row in holdings}


def tickers_held(holdings: list[dict]) -> list[str]:
    """Return unique tickers (stable order, first-seen) across all slices."""
    seen: list[str] = []
    for slice_row in holdings:
        ticker = slice_row["ticker"]
        if ticker not in seen:
            seen.append(ticker)
    return seen


def plans_for_ticker(holdings: list[dict], ticker: str) -> list[str]:
    """Return the plan_types this ticker is held under (e.g. ['SWING', 'LONGTERM'])."""
    return [row["plan_type"] for row in holdings if row["ticker"] == ticker]


def ticker_total_weight_pct(holdings: list[dict], ticker: str) -> float:
    """Sum of ``slice_weight_pct`` across all slices of a single ticker."""
    return sum(row["slice_weight_pct"] for row in holdings if row["ticker"] == ticker)


def primary_swing_slice(holdings: list[dict], ticker: str) -> dict | None:
    """Return the SWING slice for ``ticker`` if present, else the LONGTERM slice, else None.

    Preserves the MY HOLDINGS card contract: the card tracks swing cost basis,
    not the long-term average. The previous ``ORDER BY SWING-last`` hack did
    this via dict-collapse side effect; this helper does it explicitly.
    """
    return collapse_holdings_by_ticker(holdings).get(ticker)


def collapse_holdings_by_ticker(
    holdings: Iterable[Any],
) -> dict[str, dict]:
    """Return ``{ticker: slice}`` with SWING preferred when both slices exist.

    Single-pass O(N). The returned dict preserves the MY HOLDINGS contract
    (SWING cost basis wins) that the previous ``ORDER BY SWING-last`` hack
    relied on. All consumers that need dict-by-ticker access to the new
    list form route through this helper so the collapse rule lives once.
    """
    collapsed: dict[str, dict] = {}
    for slice_row in holdings:
        if not isinstance(slice_row, dict):
            continue
        ticker = slice_row.get("ticker")
        if not ticker:
            continue
        existing = collapsed.get(ticker)
        if existing is None or slice_row.get("plan_type") == "SWING":
            collapsed[ticker] = slice_row
    return collapsed


async def get_cash_balance() -> float:
    """Get current cash balance in VND."""
    db = await get_db()
    cash = await db.fetch_val("""
        SELECT avg_cost_vnd
        FROM portfolio_holdings
        WHERE UPPER(ticker) = 'CASH' AND holding_type = 'Cash'
    """)
    return float(cash) if cash is not None else 0


async def update_portfolio_prices(prices: dict[str, float]) -> int:
    """Batch update current prices for portfolio holdings (raw VND)."""
    if not prices:
        return 0

    db = await get_db()
    args_list = [(int(price), ticker.upper()) for ticker, price in prices.items()]

    try:
        await db.execute_many(
            """
            UPDATE portfolio_holdings
            SET current_price_vnd = $1, updated_at = NOW()
            WHERE ticker = $2
        """,
            args_list,
        )
        return len(args_list)
    except Exception as e:
        print(f"  [Neon] Batch price update failed: {e}")
        return 0


def _row_to_goal(row: Any) -> GoalData:
    """Convert a goals row to GoalData dict."""
    return GoalData(
        id=str(row["id"]),
        name=row["name"],
        target=row["target_vnd"],
        realized=row["realized_vnd"] or 0,
        start_date=str(row["start_date"]) if row["start_date"] else "",
        deadline=str(row["deadline"]) if row["deadline"] else "",
        goal_type=row["goal_type"],
    )


async def get_active_goal() -> GoalData | None:
    """Fetch the active goal."""
    db = await get_db()
    row = await db.fetch_one("""
        SELECT id, name, target_vnd, realized_vnd, start_date, deadline, goal_type
        FROM goals WHERE status = 'Active' LIMIT 1
    """)

    if not row:
        return None

    return _row_to_goal(row)


async def get_active_goals() -> list[GoalData]:
    """Fetch ALL active goals (no LIMIT)."""
    db = await get_db()
    rows = await db.fetch_all("""
        SELECT id, name, target_vnd, realized_vnd, start_date, deadline, goal_type
        FROM goals WHERE status = 'Active' ORDER BY deadline
    """)

    return [_row_to_goal(row) for row in rows]


async def update_goal_realized(goal_id: str, realized: float) -> bool:
    """Update the Realized field for a goal."""
    try:
        db = await get_db()
        await db.execute(
            """
            UPDATE goals SET realized_vnd = $1, updated_at = NOW()
            WHERE id = $2
        """,
            int(realized),
            goal_id,
        )
        return True
    except Exception as e:
        print(f"  [Neon] Failed to update goal: {e}")
        return False


async def get_holdings_with_sectors() -> list[dict[str, Any]]:
    """Get active holdings enriched with sector name from watchlist tables.

    Joins portfolio_holdings → swing_watchlist/longterm_watchlist → sectors
    to resolve the sector for each holding.

    Returns:
        List of dicts with ticker, plan_type, sector.
    """
    db = await get_db()
    rows = await db.fetch_all("""
        SELECT ph.ticker, ph.plan_type,
               COALESCE(s1.name, s2.name, 'Unknown') as sector
        FROM portfolio_holdings ph
        LEFT JOIN swing_watchlist sw ON sw.ticker = ph.ticker AND sw.is_active = TRUE
        LEFT JOIN sectors s1 ON s1.id = sw.sector_id
        LEFT JOIN longterm_watchlist lw ON lw.ticker = ph.ticker AND lw.is_active = TRUE
        LEFT JOIN sectors s2 ON s2.id = lw.sector_id
        WHERE ph.shares > 0 AND ph.holding_type != 'Cash'
    """)
    return [dict(r) for r in rows]


async def get_sector_allocations() -> list[dict[str, Any]]:
    """Get target sector allocations from DB."""
    db = await get_db()
    rows = await db.fetch_all(
        "SELECT sector_name, target_pct FROM sector_allocations ORDER BY target_pct DESC"
    )
    return [dict(row) for row in rows]


async def get_swing_trade_stats() -> SwingTradeStats | None:
    """Fetch closed swing trade performance stats for goal reachability model.

    Returns:
        Dict with total_trades, win_rate, expectancy_vnd, avg_holding_days,
        trades_per_month. Returns None if no closed swing trades exist.
    """
    db = await get_db()
    row = await db.fetch_one(
        "SELECT total_trades, win_rate, expectancy_vnd, avg_holding_days FROM v_swing_metrics"
    )
    if not row or not row["total_trades"]:
        return None

    total_trades = row["total_trades"]
    first_date_row = await db.fetch_one(
        "SELECT MIN(entry_date) AS first_date FROM trades_calculated WHERE status = 'CLOSED' AND plan_type = 'SWING'"
    )
    first_date = first_date_row["first_date"] if first_date_row else None
    if first_date:
        from datetime import date

        months_active = max((date.today() - first_date).days / 30.0, 1.0)
        trades_per_month = total_trades / months_active
    else:
        trades_per_month = 0.0

    return {
        "total_trades": total_trades,
        "win_rate": float(row["win_rate"] or 0),
        "expectancy_vnd": float(row["expectancy_vnd"] or 0),
        "avg_holding_days": float(row["avg_holding_days"] or 0),
        "trades_per_month": round(trades_per_month, 2),
    }


# ============================================================================
# Sync Wrappers
# ============================================================================

get_portfolio_holdings_sync = make_sync(get_portfolio_holdings)
get_portfolio_holdings_snapshot_sync = make_sync(get_portfolio_holdings_snapshot)
get_cash_balance_sync = make_sync(get_cash_balance)
update_portfolio_prices_sync = make_sync(update_portfolio_prices)
get_active_goal_sync = make_sync(get_active_goal)
update_goal_realized_sync = make_sync(update_goal_realized)
