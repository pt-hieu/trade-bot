"""ExitStrategy dispatch helpers for ``agents.picks``.

Extracted from ``picks.py`` to keep that module under the 300-line cap.
No new behaviour — this is the ATR_TRAIL branch verbatim plus the
FIXED_TARGET RR-floor check, returning a boolean pass/fail outcome.
"""

from __future__ import annotations

import logging
from typing import Literal

from shared.rules.entry_gates import check_candidate_gate
from shared.rules.exit_strategy import (
    ATR_TRAIL_STRATEGIES,
    ExitState,
    resolve_exit_strategy,
)

logger = logging.getLogger(__name__)

ExitFamilyName = Literal["FIXED_TARGET", "ATR_TRAIL"]


def apply_exit_strategy(
    *,
    ticker: str,
    strategy: str,
    setup: dict,
    tech_data: dict,
    levels: dict,
    risk_regime: str | None,
    boosted: set[str],
    min_rr: float,
    chosen_rr: float,
    rr_tolerance_pct: float = 0.0,
    stacked_shock_relief: bool = False,
) -> tuple[bool, ExitFamilyName, float]:
    """Gate + mutate setup in place per the rec's exit family.

    Returns ``(passed, exit_family, effective_rr)``. When ``passed`` is
    False the caller should skip this pick.

    ``rr_tolerance_pct`` (L5 sibling of the fundamental-screen tolerance
    band): candidates with ``chosen_rr`` inside ``[floor * (1 - tol),
    floor)`` still pass but get stamped with ``setup['rr_flag'] =
    'borderline'`` + ``borderline_reasons`` so downstream prompts can
    weigh them qualitatively. Only applies to FIXED_TARGET — ATR_TRAIL
    families have their own strategy-specific rr_gate and stay binary.
    """
    if strategy in ATR_TRAIL_STRATEGIES:
        trail_strategy = resolve_exit_strategy(strategy)
        try:
            trail_state: ExitState = trail_strategy.build_exit_state(
                levels=levels,
                close=int(setup.get("close") or tech_data.get("close") or 0),
                atr=int(tech_data.get("atr") or 0) or None,
                regime=risk_regime,
            )
        except ValueError as error:
            logger.info("picks_filter: %s dropped — atr_trail_build_failed: %s", ticker, error)
            # SWI-171 Phase A: stamp drop attribution so the picks.py audit
            # hook can read it without re-deriving the reason.
            setup["audit_drop_kind"] = "atr_trail_rr_gate"
            setup["audit_drop_reason"] = f"atr_trail_build_failed: {error}"
            return False, "ATR_TRAIL", 0.0
        trail_state["strategy"] = strategy
        trail_state["adx"] = tech_data.get("adx")
        trail_state["has_positive_catalyst"] = ticker in boosted
        if not trail_strategy.rr_gate(trail_state, min_rr):
            logger.info(
                "picks_filter: %s dropped — atr_trail_gate_fail (adx=%s, catalyst=%s)",
                ticker,
                tech_data.get("adx"),
                ticker in boosted,
            )
            setup["audit_drop_kind"] = "atr_trail_rr_gate"
            setup["audit_drop_reason"] = (
                f"atr_trail_gate_fail (adx={tech_data.get('adx')}, catalyst={ticker in boosted})"
            )
            return False, "ATR_TRAIL", 0.0
        setup["entry"] = trail_state.get("entry_price") or 0
        setup["stop"] = trail_state.get("stop_price") or 0
        setup["target"] = None
        setup["risk_reward"] = None
        setup["exit_state"] = trail_state
        setup["exit_family"] = "ATR_TRAIL"
        return True, "ATR_TRAIL", 0.0

    # Delegate the FIXED_TARGET R:R check to the shared candidate gate so
    # morning and catalyst revision read the same helper. Morning passes no
    # catalyst adjustment and no sizing floor here — position sizing is
    # applied later in extract_top_picks after conviction scaling.
    # ``stacked_shock_relief`` (L2, 2026-04-27): caller computed the
    # per-ticker flag from shock-affected ∩ HIGH/MEDIUM POSITIVE catalyst
    # count; gate caps the floor at 3.0 when True.
    gate_result = check_candidate_gate(
        trade_setup={"valid": True, "risk_reward": chosen_rr},
        rr_floor=min_rr,
        sizing_floor_vnd=0,
        stacked_shock_relief=stacked_shock_relief,
    )
    effective_floor = gate_result["effective_rr_floor"]
    if gate_result["passed"]:
        setup["exit_family"] = "FIXED_TARGET"
        setup["rr_flag"] = "pass"
        return True, "FIXED_TARGET", chosen_rr

    # Soft-band rescue (L5 sibling): candidates within tolerance of the
    # effective floor survive as borderline and carry the distance onto
    # setup so the advocate / critic / entry_strategist prompts can see
    # the miss. Hard fails (outside the band, or non-R:R reasons like
    # setup_invalid / position_below_sizing_floor) still drop.
    reason = gate_result.get("reason") or ""
    is_rr_miss = reason.startswith("rr_below_floor")
    if rr_tolerance_pct > 0 and is_rr_miss and chosen_rr > 0 and effective_floor > 0:
        soft_floor = effective_floor * (1.0 - rr_tolerance_pct)
        if chosen_rr >= soft_floor:
            miss_pct = (effective_floor - chosen_rr) / effective_floor * 100
            setup["exit_family"] = "FIXED_TARGET"
            setup["rr_flag"] = "borderline"
            setup["borderline_reasons"] = [
                f"R:R {chosen_rr:.2f} vs {effective_floor:.2f} (soft miss -{miss_pct:.0f}%)"
            ]
            logger.info(
                "picks_filter: %s borderline — rr %.2f within tolerance of floor %.2f",
                ticker,
                chosen_rr,
                effective_floor,
            )
            return True, "FIXED_TARGET", chosen_rr

    logger.info("picks_filter: %s dropped — %s", ticker, reason or "rr_gate_failed")
    # SWI-171 Phase A: stamp drop attribution. The gate's reason field
    # already discriminates rr_below_floor / position_below_sizing_floor;
    # `audit_drop_kind` maps to the gated_by enum the audit row needs.
    if reason.startswith("position_below_sizing_floor"):
        setup["audit_drop_kind"] = "sizing_floor"
    elif reason.startswith("setup_invalid"):
        # Defensive: should already have been dropped at picks.py:139.
        setup["audit_drop_kind"] = "setup_invalid"
    else:
        setup["audit_drop_kind"] = "rr_floor"
    setup["audit_drop_reason"] = reason or "rr_gate_failed"
    return False, "FIXED_TARGET", chosen_rr


__all__ = ["apply_exit_strategy"]
