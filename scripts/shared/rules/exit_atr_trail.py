"""ATRTrailExit — trend-following exit family.

Drives recs whose classified strategy is TREND, MOMENTUM, or BREAKOUT.
Uses a volatility-aware trailing stop rather than a fixed target so
catalyst-driven rallies are not truncated at the nearest resistance.

Exit geometry: entry at support; stop = support − trail_mult × ATR
(wider than MR stop so noise doesn't kick the position out of a strong
trend); no fixed target — the trailing stop replaces it; trail_mult 2.5
default (LeBeau mid-range swing). The validator gate (``rr_gate``) is
structural, not R:R based: the rec must show ADX > 25 OR an active
positive catalyst OR be a BREAKOUT, and the stop cannot imply a loss
larger than max(12%, 2 × HOSE daily band).
"""

from __future__ import annotations

import logging
from typing import ClassVar

from shared.rules.exit_strategy import (
    HOSE_DAILY_BAND_PCT,
    AlertTrigger,
    ExitEvalResult,
    ExitFamilyName,
    ExitState,
    TrailBar,
)
from shared.rules.trail_sim import compute_trail_level, hose_floor_limit, simulate_atr_trail

logger = logging.getLogger(__name__)

# ATR multiplier for the initial hard stop and the running trail.
_DEFAULT_TRAIL_MULT: float = 2.5

# Absolute loss cap: stop cannot imply loss larger than this (as a fraction
# of entry). The effective cap is max(_MIN_LOSS_CAP, 2 × daily_limit_pct).
_MIN_LOSS_CAP: float = 0.12

# Minimum ADX reading accepted by rr_gate as evidence of trend strength.
_ADX_TREND_THRESHOLD: float = 25.0


class ATRTrailExit:
    """Exit family for TREND / MOMENTUM / BREAKOUT."""

    name: ClassVar[ExitFamilyName] = "ATR_TRAIL"

    def build_exit_state(
        self,
        levels: dict,
        close: int,
        atr: int | None,
        regime: str | None,
    ) -> ExitState:
        """Build a trail-aware ExitState. Raises ValueError on insufficient inputs."""
        if atr is None or atr <= 0:
            raise ValueError(
                f"ATRTrailExit.build_exit_state requires a positive ATR; got atr={atr}."
            )
        # SWI-3a: prefer MA-free `nearest_swing_low` so the trail anchor
        # never collapses to a moving average sitting just below price.
        support = (
            levels.get("nearest_swing_low")
            or levels.get("nearest_support")
            or levels.get("swing_low")
        )
        if not support:
            raise ValueError(
                "ATRTrailExit requires nearest_swing_low, nearest_support, or swing_low"
            )

        entry = int(support)
        stop_raw = int(round(support - _DEFAULT_TRAIL_MULT * atr))
        max_loss_pct = max(_MIN_LOSS_CAP, 2 * HOSE_DAILY_BAND_PCT)
        floor_stop = int(round(entry * (1.0 - max_loss_pct)))
        stop = max(stop_raw, floor_stop)

        return ExitState(
            entry_price=entry,
            stop_price=stop,
            target_price=None,
            atr_at_entry=int(atr),
            trail_mult=_DEFAULT_TRAIL_MULT,
            peak_price=None,
            strategy=None,
            adx=None,
            has_positive_catalyst=False,
            daily_limit_pct=HOSE_DAILY_BAND_PCT,
        )

    def evaluate_bars(
        self,
        state: ExitState,
        bars: list[TrailBar],
        entry_date: str,
    ) -> ExitEvalResult:
        """Thin wrapper around ``simulate_atr_trail``."""
        atr = state.get("atr_at_entry") or 0
        trail_mult = state.get("trail_mult") or _DEFAULT_TRAIL_MULT
        entry = state.get("entry_price") or 0
        stop = state.get("stop_price") or 0

        if atr <= 0:
            raise ValueError(
                f"ATR_TRAIL evaluate_bars requires atr_at_entry>0, got {atr}. "
                "Fail-loudly: this rec should not have been persisted."
            )
        trail = simulate_atr_trail(
            bars=bars,
            entry_price=entry,
            stop_price=stop,
            atr_at_entry=atr,
            trail_mult=trail_mult,
            entry_date=entry_date,
        )
        stop_hit = trail.status == "LOSS" and trail.exit_price == stop
        return ExitEvalResult(
            entry_hit=trail.status != "MISSED",
            stop_hit=stop_hit,
            target_hit=False,  # ATR_TRAIL has no fixed target
            exit_price=trail.exit_price,
            status=trail.status,
            peak_price=trail.peak_price,
            pnl_percent=trail.pnl_percent,
            days_in_trade=trail.days_in_trade,
            suspended_days=trail.suspended_days,
            exit_date=trail.exit_date,
        )

    def alert_condition(
        self,
        state: ExitState,
        current_price: int,
        prev_close: int,
    ) -> AlertTrigger | None:
        """Polls the trail. Updates state['peak_price'] when a new high arrives.

        Caller should persist the (possibly updated) peak after this call —
        comparing the pre/post values tells them whether a DB write is
        needed. Misconfigured state (missing ATR / entry / stop) is logged
        loudly rather than silently no-oped, since a rec reaching this path
        with bad data implies a pipeline bug upstream.
        """
        atr = state.get("atr_at_entry") or 0
        trail_mult = state.get("trail_mult") or _DEFAULT_TRAIL_MULT
        stop = state.get("stop_price") or 0
        entry = state.get("entry_price") or 0

        if atr <= 0 or entry <= 0 or stop <= 0:
            logger.warning(
                "ATR_TRAIL alert_condition called with bad state: atr=%s entry=%s stop=%s",
                atr,
                entry,
                stop,
            )
            return None

        peak = state.get("peak_price") or entry
        if current_price > peak:
            state["peak_price"] = current_price
            peak = current_price

        trail_level = compute_trail_level(peak, atr, trail_mult, stop)
        if current_price > trail_level:
            return None

        if prev_close > 0 and current_price <= hose_floor_limit(prev_close):
            return AlertTrigger(
                kind="LIKELY_FLOOR_LOCKED",
                level_price=current_price,
                rationale=(
                    f"Price {current_price:,} at HOSE floor (prev_close "
                    f"{prev_close:,}) with trail breached at {trail_level:,}"
                ),
            )

        kind = "STOP_HIT" if current_price <= stop else "TRAIL_BREAK"
        return AlertTrigger(
            kind=kind,
            level_price=trail_level if kind == "TRAIL_BREAK" else stop,
            rationale=(
                f"Price {current_price:,} broke trail {trail_level:,} "
                f"(peak {peak:,}, ATR {atr:,}, mult {trail_mult})"
            ),
        )

    def rr_gate(self, state: ExitState, rr_floor: float) -> bool:
        """Structural gate — ADX > 25 OR positive catalyst OR BREAKOUT.

        ``rr_floor`` is accepted for Protocol parity but deliberately unused:
        trailing-stop recs have no fixed target to compute R:R against.
        """
        entry = state.get("entry_price") or 0
        stop = state.get("stop_price") or 0
        atr = state.get("atr_at_entry") or 0
        if entry <= 0 or stop <= 0 or atr <= 0 or stop >= entry:
            return False

        daily_limit_pct = state.get("daily_limit_pct") or HOSE_DAILY_BAND_PCT
        max_loss_pct = max(_MIN_LOSS_CAP, 2 * daily_limit_pct)
        implied_loss_pct = (entry - stop) / entry
        if implied_loss_pct > max_loss_pct + 1e-6:
            logger.info(
                "ATR_TRAIL rr_gate dropped: implied loss %.1f%% > cap %.1f%%",
                implied_loss_pct * 100,
                max_loss_pct * 100,
            )
            return False

        adx = state.get("adx")
        strategy = (state.get("strategy") or "").upper()
        has_catalyst = bool(state.get("has_positive_catalyst"))

        trend_strength = adx is not None and adx >= _ADX_TREND_THRESHOLD
        return trend_strength or has_catalyst or strategy == "BREAKOUT"

    def exit_description(self, state: ExitState) -> str | None:
        trail_mult = state.get("trail_mult") or _DEFAULT_TRAIL_MULT
        stop = state.get("stop_price") or 0
        atr = state.get("atr_at_entry") or 0
        if stop <= 0 or atr <= 0:
            return None
        return (
            f"Trail {trail_mult:.1f}x ATR from peak "
            f"(hard stop {stop / 1000:.1f}k, ATR {atr / 1000:.2f}k)"
        )

    def to_db_row(self, state: ExitState) -> dict[str, int | float | None]:
        """ATR_TRAIL leaves target_price_vnd NULL; writes atr/trail fields."""
        return {
            "entry_price_vnd": state.get("entry_price") or None,
            "stop_price_vnd": state.get("stop_price") or None,
            "target_price_vnd": None,
            "atr_at_entry_vnd": state.get("atr_at_entry") or None,
            "trail_mult": state.get("trail_mult"),
        }


__all__ = ["ATRTrailExit"]
