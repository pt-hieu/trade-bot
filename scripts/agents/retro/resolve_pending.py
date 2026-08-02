"""
Resolve PENDING evaluations over multi-day holding period.

Entry-day evaluation (``compute.py:_evaluate_single``) only checks if
target/stop was hit on the recommendation date. Swing trades need
multi-day evaluation. This module is pure computation — no DB writes.

Stop semantics: day-N bars resolve intraday (``low <= stop_price``).
``compute.py`` resolves day-0 EOD only (overnight gap noise). Keep both
modules in lockstep — see ``compute.py`` docstring for the full
divergence rationale.

ExitStrategy dispatch:
    FIXED_TARGET → stop/target binary check (stop-wins-on-tie).
    ATR_TRAIL    → full trailing-stop simulation via trail_sim.

Resolution priority per day (FIXED_TARGET, chronological):
  1. If low <= stop_price → LOSS (even if high >= target same day)
  2. If high >= target_price → WIN
  3. Otherwise continue to next day
  4. After max holding period → remains PENDING

ATR_TRAIL windows are typically longer (trends need room to run) — callers
pass ``max_holding_days`` explicitly when dispatching through this path.
"""

from __future__ import annotations

import logging

from shared.rules.exit_strategy import (
    ATR_TRAIL_STRATEGIES,
    ExitState,
    TrailBar,
    resolve_exit_strategy,
)

logger = logging.getLogger(__name__)

# Max trading days to check after entry day (FIXED_TARGET default)
MAX_HOLDING_DAYS = 5

# ATR_TRAIL trends run longer — default window is wider so the trail has
# room to activate. Caller may override via resolve_pending_evaluations.
MAX_HOLDING_DAYS_ATR_TRAIL = 15


def resolve_pending_evaluations(
    pending_evals: list[dict],
    price_data: dict[str, list[dict]],
    max_holding_days_atr_trail: int = MAX_HOLDING_DAYS_ATR_TRAIL,
) -> list[tuple[str, str, float]]:
    """Resolve PENDING evaluations using multi-day OHLC data.

    Args:
        pending_evals: List of PENDING evaluation dicts with keys:
            id, ticker, entry_price_vnd, stop_price_vnd, target_price_vnd,
            record_date (date the recommendation was made), strategy,
            atr_at_entry_vnd (ATR_TRAIL only), trail_mult (ATR_TRAIL only).
        price_data: Dict mapping ticker → list of daily OHLC dicts
            (sorted chronologically, each with: date, open, high, low, close).
            Only includes days AFTER the recommendation date.
        max_holding_days_atr_trail: Window size for ATR_TRAIL simulation.

    Returns:
        List of (eval_id, new_status, pnl_percent) tuples for resolved evals.
        Unresolved evals (still PENDING) are not included.
    """
    resolutions: list[tuple[str, str, float]] = []

    for evaluation in pending_evals:
        eval_id = evaluation["id"]
        ticker = evaluation["ticker"]
        entry_price = evaluation.get("entry_price_vnd")

        if not entry_price or entry_price <= 0:
            continue

        ticker_prices = price_data.get(ticker) or []
        if not ticker_prices:
            logger.debug("No price data for %s — skipping", ticker)
            continue

        strategy = (evaluation.get("strategy") or "").upper()
        is_atr_trail = strategy in ATR_TRAIL_STRATEGIES

        if is_atr_trail:
            resolution = _resolve_atr_trail(
                evaluation,
                ticker_prices[:max_holding_days_atr_trail],
            )
        else:
            resolution = _resolve_fixed_target(
                eval_id=eval_id,
                ticker=ticker,
                entry_price=entry_price,
                stop_price=evaluation.get("stop_price_vnd"),
                target_price=evaluation.get("target_price_vnd"),
                daily_prices=ticker_prices[:MAX_HOLDING_DAYS],
            )
        if resolution:
            resolutions.append(resolution)

    logger.info(
        "Resolved %d of %d PENDING evaluations",
        len(resolutions),
        len(pending_evals),
    )
    return resolutions


def _resolve_atr_trail(
    evaluation: dict,
    daily_prices: list[dict],
) -> tuple[str, str, float] | None:
    """Dispatch to ATRTrailExit.evaluate_bars. Fail loud when ATR missing."""
    eval_id = evaluation["id"]
    ticker = evaluation["ticker"]
    atr_at_entry = evaluation.get("atr_at_entry_vnd")
    if not atr_at_entry or atr_at_entry <= 0:
        # Per CLAUDE.md: fail loudly — do not silently downgrade to FIXED_TARGET.
        logger.warning(
            "ATR_TRAIL PENDING %s %s missing atr_at_entry_vnd=%r — "
            "retro cannot simulate trail; leaving unresolved",
            eval_id[:8],
            ticker,
            atr_at_entry,
        )
        return None

    state: ExitState = {
        "entry_price": int(evaluation["entry_price_vnd"]),
        "stop_price": int(evaluation.get("stop_price_vnd") or 0),
        "target_price": None,
        "atr_at_entry": int(atr_at_entry),
        "trail_mult": float(evaluation.get("trail_mult") or 2.5),
        "peak_price": None,
    }
    bars: list[TrailBar] = [
        TrailBar(
            date=day.get("date") or "",
            open=int(day.get("open") or 0),
            high=int(day.get("high") or 0),
            low=int(day.get("low") or 0),
            close=int(day.get("close") or 0),
        )
        for day in daily_prices
    ]
    entry_date = evaluation.get("record_date") or ""
    strategy = resolve_exit_strategy(evaluation.get("strategy"))
    result = strategy.evaluate_bars(state, bars, str(entry_date))

    status = result.get("status") or "PENDING"
    if status == "PENDING":
        return None
    pnl = result.get("pnl_percent") or 0.0
    # ATRTrailExit statuses map: TRAIL_FLOOR_LOCK → WIN/LOSS by pnl sign.
    if status == "TRAIL_FLOOR_LOCK":
        status = "WIN" if pnl >= 0 else "LOSS"
    logger.info(
        "PENDING %s %s %s → %s (exit %s on %s, pnl=%.2f%%)",
        eval_id[:8],
        ticker,
        evaluation.get("strategy"),
        status,
        result.get("exit_price"),
        result.get("exit_date"),
        pnl,
    )
    return (eval_id, status, pnl)


def _resolve_fixed_target(
    eval_id: str,
    ticker: str,
    entry_price: float,
    stop_price: float | None,
    target_price: float | None,
    daily_prices: list[dict],
) -> tuple[str, str, float] | None:
    """Multi-day stop/target binary check for post-entry FIXED_TARGET recs.

    Bars here are days AFTER the recommendation date (entry already filled
    on day 0, upstream). FixedTargetExit.evaluate_bars assumes day 0 is the
    entry day, so it cannot be reused directly — the semantics differ.
    """
    for day in daily_prices:
        day_low = day.get("low") or 0
        day_high = day.get("high") or 0

        if day_low <= 0 or day_high <= 0:
            continue

        if stop_price and stop_price > 0 and day_low <= stop_price:
            pnl = round((stop_price - entry_price) / entry_price * 100, 2)
            logger.info(
                "PENDING %s %s -> LOSS (stop %.0f hit on %s, pnl=%.2f%%)",
                eval_id[:8],
                ticker,
                stop_price,
                day.get("date", "?"),
                pnl,
            )
            return (eval_id, "LOSS", pnl)

        if target_price and target_price > 0 and day_high >= target_price:
            pnl = round((target_price - entry_price) / entry_price * 100, 2)
            logger.info(
                "PENDING %s %s -> WIN (target %.0f hit on %s, pnl=%.2f%%)",
                eval_id[:8],
                ticker,
                target_price,
                day.get("date", "?"),
                pnl,
            )
            return (eval_id, "WIN", pnl)

    return None
