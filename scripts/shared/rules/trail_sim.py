"""Pure deterministic ATR trailing-stop simulator.

Used by retro (``daily_evaluations`` rows) and by integration tests. No async,
no DB, no LLM. All prices are VND integers; ATR is a VND integer.

Trail formula
-------------
For each bar after entry (chronological, only days where the ticker traded):

    peak  ← max(peak, bar.high)
    trail ← max(peak − trail_mult × atr_at_entry, hard_stop)

Exit priority on the bar:
    1. bar.open at or below HOSE floor (≈ round(prev_close × 0.93)) AND
       trail/stop is already above the open   → TRAIL_FLOOR_LOCK (exit at open)
    2. bar.low ≤ hard_stop                    → LOSS (exit at hard_stop,
                                                  capped at bar.open on gap-downs)
    3. bar.low ≤ trail                        → WIN (exit at trail, capped at
                                                  bar.open on gap-downs)
    4. Otherwise advance peak and continue.

End of window without an exit → PENDING (caller may widen the window).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .exit_strategy import HOSE_DAILY_BAND_PCT, TrailBar

TrailStatus = Literal["WIN", "LOSS", "PENDING", "MISSED", "TRAIL_FLOOR_LOCK"]


@dataclass(frozen=True)
class TrailResult:
    status: TrailStatus
    exit_price: int | None  # VND; None when PENDING or MISSED
    exit_date: str | None  # ISO
    peak_price: int  # VND; highest high seen during window
    days_in_trade: int  # trading days counted (bars consumed)
    suspended_days: int  # dates expected but missing (see _count_gaps)
    pnl_percent: float | None  # whole-number percent


def simulate_atr_trail(
    bars: list[TrailBar],
    entry_price: int,
    stop_price: int,
    atr_at_entry: int,
    trail_mult: float,
    entry_date: str,
) -> TrailResult:
    """Run the trailing-stop simulation.

    Caller contract: ``bars`` is chronologically ordered, covers the window
    STARTING FROM ``entry_date`` (inclusive). The first bar is the entry
    candidate: if its low never touches ``entry_price`` it is treated as
    MISSED. All bars already exclude weekends/holidays.
    """
    if atr_at_entry <= 0 or trail_mult <= 0:
        raise ValueError(
            f"ATR_TRAIL requires atr_at_entry>0 and trail_mult>0 — "
            f"got atr={atr_at_entry}, trail_mult={trail_mult}"
        )
    if not bars:
        return TrailResult(
            status="MISSED",
            exit_price=None,
            exit_date=None,
            peak_price=entry_price,
            days_in_trade=0,
            suspended_days=0,
            pnl_percent=None,
        )

    # Day 0 — entry bar. Enter only if the bar traded through entry_price.
    first = bars[0]
    first_low = int(first.get("low") or 0)
    first_high = int(first.get("high") or 0)
    if first_low <= 0 or first_high <= 0 or first_low > entry_price:
        return TrailResult(
            status="MISSED",
            exit_price=None,
            exit_date=first.get("date"),
            peak_price=max(first_high, entry_price),
            days_in_trade=0,
            suspended_days=0,
            pnl_percent=None,
        )

    peak = first_high
    prev_close = int(first.get("close") or entry_price)
    # Check entry-day intrabar exits — gap/stop on the entry bar itself.
    if first_low <= stop_price:
        exit_price = min(int(first.get("open") or stop_price), stop_price)
        return _loss_result(entry_price, exit_price, first.get("date"), peak, 1)

    suspended_days = 0

    for index, bar in enumerate(bars[1:], start=1):
        bar_open = int(bar.get("open") or 0)
        bar_high = int(bar.get("high") or 0)
        bar_low = int(bar.get("low") or 0)
        bar_close = int(bar.get("close") or 0)
        bar_date = bar.get("date")

        if bar_open <= 0 or bar_high <= 0 or bar_low <= 0:
            suspended_days += 1
            continue

        floor_limit = _hose_floor_limit(prev_close)
        trail_level = _trail_level(peak, atr_at_entry, trail_mult, stop_price)

        # 1. HOSE floor-lock: open at/below floor AND trail would've fired.
        if bar_open <= floor_limit and trail_level >= bar_open:
            days_in_trade = index + 1
            pnl = _pct(bar_open, entry_price)
            return TrailResult(
                status="TRAIL_FLOOR_LOCK",
                exit_price=bar_open,
                exit_date=bar_date,
                peak_price=peak,
                days_in_trade=days_in_trade,
                suspended_days=suspended_days,
                pnl_percent=pnl,
            )

        # 2. Hard stop wins over trail. Gap-down clamps exit at open.
        if bar_low <= stop_price:
            exit_price = min(bar_open, stop_price) if bar_open < stop_price else stop_price
            return _loss_result(entry_price, exit_price, bar_date, peak, index + 1, suspended_days)

        # 3. Trailing-stop break.
        if bar_low <= trail_level:
            exit_price = min(bar_open, trail_level) if bar_open < trail_level else trail_level
            pnl = _pct(exit_price, entry_price)
            status: TrailStatus = "WIN" if exit_price > entry_price else "LOSS"
            return TrailResult(
                status=status,
                exit_price=exit_price,
                exit_date=bar_date,
                peak_price=peak,
                days_in_trade=index + 1,
                suspended_days=suspended_days,
                pnl_percent=pnl,
            )

        peak = max(peak, bar_high)
        prev_close = bar_close or prev_close

    # Window exhausted without an exit.
    return TrailResult(
        status="PENDING",
        exit_price=None,
        exit_date=None,
        peak_price=peak,
        days_in_trade=len(bars),
        suspended_days=suspended_days,
        pnl_percent=None,
    )


def compute_trail_level(peak: int, atr_at_entry: int, trail_mult: float, hard_stop: int) -> int:
    """Return the trailing-stop price for a given peak. Never below hard_stop.

    Shared with ``ATRTrailExit.alert_condition`` — single source of truth
    for the trail-break computation across retro and live alert paths.
    """
    raw = round(peak - trail_mult * atr_at_entry)
    return max(raw, hard_stop)


def hose_floor_limit(prev_close: int) -> int:
    """HOSE daily lower band. Conservative rounding to VND int."""
    return round(prev_close * (1.0 - HOSE_DAILY_BAND_PCT))


# Retained aliases for internal callers using the old private names.
_trail_level = compute_trail_level
_hose_floor_limit = hose_floor_limit


def _pct(exit_price: int, entry_price: int) -> float:
    if entry_price <= 0:
        return 0.0
    return round((exit_price - entry_price) / entry_price * 100, 2)


def _loss_result(
    entry_price: int,
    exit_price: int,
    exit_date: str | None,
    peak: int,
    days_in_trade: int,
    suspended_days: int = 0,
) -> TrailResult:
    return TrailResult(
        status="LOSS",
        exit_price=exit_price,
        exit_date=exit_date,
        peak_price=peak,
        days_in_trade=days_in_trade,
        suspended_days=suspended_days,
        pnl_percent=_pct(exit_price, entry_price),
    )


__all__ = [
    "TrailResult",
    "TrailStatus",
    "compute_trail_level",
    "hose_floor_limit",
    "simulate_atr_trail",
]
