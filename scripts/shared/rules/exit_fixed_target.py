"""FixedTargetExit — canonical mean-reversion / bounce / pullback exit family.

Encapsulates the existing entry/stop/target semantics exactly as they were
before the ExitStrategy refactor. The heavyweight level-resolution logic
(resistance scanning, aggressive vs conservative target chooser, pullback
promotion) still lives in ``agents.tools.technicals.compute_setup_from_levels``
— this class is the thin adapter that:

    1. consumes the levels dict through the existing pure function,
    2. converts its flat entry/stop/target/risk_reward output into an ExitState,
    3. provides per-bar / per-poll / per-validator dispatch methods used by
       retro, midday, alert monitor, and the validator.

This split keeps ``technicals.py`` as the single source of truth for level
mathematics while making exit dispatch polymorphic. No behaviour change on
the MR path — byte-for-byte identical DB rows for existing strategies.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from shared.rules.exit_strategy import (
    AlertTrigger,
    ExitEvalResult,
    ExitFamilyName,
    ExitState,
    TrailBar,
)

logger = logging.getLogger(__name__)


class FixedTargetExit:
    """Exit family for MR / BOUNCE / PULLBACK / DIVERGENCE / UNCLASSIFIED."""

    name: ClassVar[ExitFamilyName] = "FIXED_TARGET"

    def build_exit_state(
        self,
        levels: dict,
        close: int,
        atr: int | None,
        regime: str | None,
    ) -> ExitState:
        """Delegates to ``compute_setup_from_levels`` and flattens the result.

        ``atr`` and ``regime`` are forwarded so existing regime-scaled target
        behaviour (CALM expands, RISK_OFF contracts) is preserved.
        """
        from agents.tools.technicals import compute_setup_from_levels

        setup = compute_setup_from_levels(
            levels,
            close,
            ticker="",
            structural_uptrend=False,
            atr=atr,
            risk_regime=regime,
        )
        if "error" in setup or not setup.get("valid"):
            return ExitState(
                entry_price=0,
                stop_price=0,
                target_price=None,
                atr_at_entry=None,
                trail_mult=None,
                peak_price=None,
            )
        return ExitState(
            entry_price=int(setup["entry"]),
            stop_price=int(setup["stop"]),
            target_price=int(setup["target"]),
            atr_at_entry=None,
            trail_mult=None,
            peak_price=None,
        )

    def evaluate_bars(
        self,
        state: ExitState,
        bars: list[TrailBar],
        entry_date: str,
    ) -> ExitEvalResult:
        """Same-day single-EOD check, falling through subsequent days.

        Matches ``retro/compute.py::_evaluate_single`` for the entry bar and
        ``retro/resolve_pending.py::_resolve_single`` for subsequent days
        (stop-before-target priority if both hit on the same bar).
        """
        entry = state.get("entry_price") or 0
        stop = state.get("stop_price") or 0
        target = state.get("target_price") or 0
        if entry <= 0 or not bars:
            return ExitEvalResult(
                entry_hit=False,
                stop_hit=False,
                target_hit=False,
                exit_price=None,
                status="MISSED",
                peak_price=None,
                pnl_percent=None,
                days_in_trade=None,
                suspended_days=0,
                exit_date=None,
            )

        peak = 0
        suspended_days = 0
        first_bar_hit = False

        for index, bar in enumerate(bars):
            bar_high = int(bar.get("high") or 0)
            bar_low = int(bar.get("low") or 0)
            bar_date = bar.get("date")

            if bar_high <= 0 or bar_low <= 0:
                suspended_days += 1
                continue

            peak = max(peak, bar_high)

            # Entry fill check on bar 0 (same-day) or later bars for PENDING.
            if not first_bar_hit:
                first_bar_hit = bar_low <= entry
                if not first_bar_hit and index == 0:
                    # Never hit on the entry day — continues as PENDING for
                    # multi-day resolution (matches resolve_pending_evaluations).
                    continue

            if stop > 0 and bar_low <= stop:
                pnl = round((stop - entry) / entry * 100, 2) if entry else 0.0
                return ExitEvalResult(
                    entry_hit=True,
                    stop_hit=True,
                    target_hit=False,
                    exit_price=stop,
                    status="LOSS",
                    peak_price=peak,
                    pnl_percent=pnl,
                    days_in_trade=index + 1,
                    suspended_days=suspended_days,
                    exit_date=bar_date,
                )
            if target > 0 and bar_high >= target:
                pnl = round((target - entry) / entry * 100, 2) if entry else 0.0
                return ExitEvalResult(
                    entry_hit=True,
                    stop_hit=False,
                    target_hit=True,
                    exit_price=target,
                    status="WIN",
                    peak_price=peak,
                    pnl_percent=pnl,
                    days_in_trade=index + 1,
                    suspended_days=suspended_days,
                    exit_date=bar_date,
                )

        if not first_bar_hit:
            return ExitEvalResult(
                entry_hit=False,
                stop_hit=False,
                target_hit=False,
                exit_price=None,
                status="MISSED",
                peak_price=peak or None,
                pnl_percent=None,
                days_in_trade=None,
                suspended_days=suspended_days,
                exit_date=None,
            )

        last = bars[-1]
        close_val = int(last.get("close") or 0)
        pnl = round((close_val - entry) / entry * 100, 2) if entry and close_val else None
        return ExitEvalResult(
            entry_hit=True,
            stop_hit=False,
            target_hit=False,
            exit_price=None,
            status="PENDING",
            peak_price=peak or None,
            pnl_percent=pnl,
            days_in_trade=len(bars),
            suspended_days=suspended_days,
            exit_date=None,
        )

    def alert_condition(
        self,
        state: ExitState,
        current_price: int,
        prev_close: int,
    ) -> AlertTrigger | None:
        """Fires on target breach or stop breach."""
        stop = state.get("stop_price") or 0
        target = state.get("target_price") or 0
        if stop > 0 and current_price <= stop:
            return AlertTrigger(
                kind="STOP_HIT",
                level_price=stop,
                rationale=f"Price {current_price:,} broke stop {stop:,}",
            )
        if target > 0 and current_price >= target:
            return AlertTrigger(
                kind="TARGET_HIT",
                level_price=target,
                rationale=f"Price {current_price:,} reached target {target:,}",
            )
        return None

    def rr_gate(self, state: ExitState, rr_floor: float) -> bool:
        """Net-of-cost R:R comparison — preserves pre-refactor validator logic."""
        entry = state.get("entry_price") or 0
        stop = state.get("stop_price") or 0
        target = state.get("target_price") or 0
        if entry <= 0 or stop <= 0 or target <= 0 or stop >= entry or target <= entry:
            return False
        # Reuse compute_net_rr for cost parity with the pre-refactor validator.
        # Trading config may not be initialised in unit tests — fall back to
        # zero cost in that case; production paths always have the config up.
        from shared.rules.rr_math import compute_net_rr_only

        cost_pct: float = 0.0
        try:
            from shared.trading_config import get_trading_config

            cost_pct = get_trading_config().transaction_cost_pct or 0.0
        except RuntimeError:
            pass
        rr = compute_net_rr_only(entry, stop, target, cost_pct) or 0.0
        return rr >= rr_floor

    def exit_description(self, state: ExitState) -> str | None:
        target = state.get("target_price") or 0
        entry = state.get("entry_price") or 0
        stop = state.get("stop_price") or 0
        if target <= 0 or entry <= 0 or stop <= 0 or entry <= stop:
            return None
        rr = (target - entry) / (entry - stop)
        return f"Target {target / 1000:.1f}k (R:R {rr:.1f})"

    def to_db_row(self, state: ExitState) -> dict[str, int | float | None]:
        """Return DB column-name → value mapping for INSERT merge.

        FIXED_TARGET leaves trail fields NULL so the DB distinguishes it
        unambiguously from ATR_TRAIL rows.
        """
        return {
            "entry_price_vnd": state.get("entry_price") or None,
            "stop_price_vnd": state.get("stop_price") or None,
            "target_price_vnd": state.get("target_price") or None,
            "atr_at_entry_vnd": None,
            "trail_mult": None,
        }


__all__ = ["FixedTargetExit"]
