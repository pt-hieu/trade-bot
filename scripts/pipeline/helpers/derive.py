"""Async orchestrators that compose rules + io into pipeline-stage helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date
from typing import TYPE_CHECKING

from shared.errors import report_caught
from shared.neon import get_market_regime, get_sector_rotation
from shared.observability import span

from ..types import PhaseIntermediates
from .rules import ProducerLeakError, extract_risk_regime, reconcile_regimes

if TYPE_CHECKING:
    from shared.rules.catalyst_override import CatalystInput

    from ..types import FlatTechnicalsRow

logger = logging.getLogger(__name__)


async def get_market_level(
    scan_date,
    vnindex_technicals: FlatTechnicalsRow | dict | None = None,
    rotation_context: str = "",
    learnings_context: str = "",
):
    """Get market level analysis (load existing from DB or generate via agent)."""
    existing = await get_market_regime(scan_date)
    if "error" not in existing:
        return existing
    from agents import classify_regime_with_agent

    return await classify_regime_with_agent(
        scan_date,
        vnindex_technicals=vnindex_technicals,
        rotation_context=rotation_context,
        learnings_context=learnings_context,
    )


async def load_sector_rotation(scan_date, market_regime: str | None = None):
    """Load today's sector rotation from database.

    If market_regime is provided and the rotation doesn't have one,
    backfills it to avoid repeated caller-side fixup.
    """
    result = await get_sector_rotation(scan_date)
    if "error" in result:
        return None
    if market_regime and not result.get("market_regime"):
        result["market_regime"] = market_regime
    return result


async def derive_intermediates(
    *,
    raw_regime: str,
    macro_metrics: dict | None,
    early_mode: str,
    sector_rotation: dict | None,
    trailing_stops_context: str,
    technicals: dict,
    geopolitical_context: str,
    market_level: dict | None = None,
) -> PhaseIntermediates:
    """Single source of truth for Phase 1→Phase 3 intermediate derivation.

    Called by both live and resume paths after they load their raw data.
    """
    from shared.calibration_overlay import init_calibration_overlay
    from shared.rules.entry_gates import determine_entry_gate

    global_risk_regime = extract_risk_regime(macro_metrics)
    market_regime = reconcile_regimes(raw_regime, global_risk_regime)
    if raw_regime != market_regime:
        raise ProducerLeakError(
            f"regime drift: raw={raw_regime!r} reconciled={market_regime!r} "
            f"global_risk={global_risk_regime!r}"
        )

    await init_calibration_overlay(regime=global_risk_regime)

    gate = determine_entry_gate(early_mode, global_risk_regime=global_risk_regime)

    if gate.entries_blocked_reason:
        print(f"  [Regime Gate] {gate.entries_blocked_reason}")

    return PhaseIntermediates(
        market_regime=market_regime,
        global_risk_regime=global_risk_regime,
        entries_allowed=gate.entries_allowed,
        entries_blocked_reason=gate.entries_blocked_reason,
        early_mode=early_mode,
        sector_rotation=sector_rotation,
        trailing_stops_context=trailing_stops_context,
        geopolitical_context=geopolitical_context,
        technicals=technicals,
    )


async def compose_gate_from_state(
    *,
    intermediates: PhaseIntermediates,
    macro_metrics: dict | None,
    pipeline_constraints: dict,
    trading_mode: str,
    scan_date: date,
    strategy_director_failed: bool = False,
    active_catalysts: list[CatalystInput] | None = None,
    sector_beliefs: list[dict] | None = None,
    candidate_universe: Iterable[str] | None = None,
):
    """Compose today's full RecommendationGateDecision and mutate intermediates."""
    from datetime import timedelta

    from shared.neon.streak_alert import get_streak_alert
    from shared.rules.catalyst_override import (
        has_high_positive_macro_blanket_catalyst,
        has_high_positive_per_ticker_catalyst,
    )
    from shared.rules.entry_gates import is_trading_mode_healthy
    from shared.rules.geopolitical import ACTIVE_SHOCK_PHASES
    from shared.rules.macro_stress import classify_underlying_stress
    from shared.rules.recommendation_gate import compose_recommendation_gate

    # T-1 read offset is load-bearing (see commit da47dc62).
    #   - ``streak_alert_json`` on Day N+1's row reflects today's retro
    #     (post-EOD, after this gate has already run).
    #   - ``gate_decision_json.inputs_digest.streak_alert`` freezes
    #     yesterday's retro snapshot at gate-decision time, which is
    #     exactly what this read returns.
    # Cross-column length/start_date divergence on a record_date row is
    # the EXPECTED two-phase write signature. Only ``gate_profile``
    # divergence between the two snapshots is a regression signal.
    # 2026-05-13 incident: post-retro deletion of a transient false-BUY
    # rec produced exactly this signature; pipeline-review misclassified
    # it as a CRITICAL split-brain bug.
    try:
        streak_alert = await get_streak_alert(scan_date - timedelta(days=1))
    except Exception as exc:
        logger.warning("Streak alert fetch failed (non-fatal): %s", exc)
        streak_alert = None

    underlying_stress = classify_underlying_stress(macro_metrics)
    macro_relief = has_high_positive_macro_blanket_catalyst(active_catalysts)

    shock_phase = (macro_metrics or {}).get("geopolitical_shock") or {}
    shock_active = (shock_phase.get("phase_name") or "") in ACTIVE_SHOCK_PHASES

    bullish_count = sum(
        1
        for belief in (sector_beliefs or [])
        if (belief.get("direction") or "").upper() == "BULLISH"
    )

    per_ticker_positive = has_high_positive_per_ticker_catalyst(
        active_catalysts, candidate_universe or []
    )

    cash_healthy = is_trading_mode_healthy(trading_mode)

    decision = compose_recommendation_gate(
        trading_mode=trading_mode,
        market_regime=intermediates.market_regime,
        global_risk_regime=intermediates.global_risk_regime,
        urgency_tier=pipeline_constraints.get("urgency_tier") or "NORMAL",
        urgency_min_rr=pipeline_constraints.get("min_rr") or 2.5,
        urgency_max_picks=pipeline_constraints.get("max_new_entries") or 3,
        underlying_stress=underlying_stress,
        strategy_director_failed=strategy_director_failed,
        retro_min_rr_override=pipeline_constraints.get("retro_min_rr_override"),
        retro_max_entries=pipeline_constraints.get("retro_max_entries"),
        expectancy_floor=pipeline_constraints.get("expectancy_floor"),
        streak_alert=streak_alert,
        has_high_positive_macro_catalyst=macro_relief,
        bullish_sector_belief_count=bullish_count,
        has_candidate_positive_catalyst=per_ticker_positive,
        shock_active=shock_active,
        cash_healthy=cash_healthy,
    )

    intermediates.gate_decision = decision
    intermediates.streak_alert = streak_alert
    intermediates.entries_allowed = decision.entries_allowed
    if decision.entries_blocked_reason:
        intermediates.entries_blocked_reason = decision.entries_blocked_reason
    logger.info(
        "Gate compose: floor R:R %.1f, max_entries %d, entries_allowed=%s, rules=%s",
        decision.effective_rr_floor,
        decision.max_new_entries,
        decision.entries_allowed,
        list(decision.applied_rules),
    )
    return decision


async def resolve_trading_mode(
    early_mode,
    deployable_cash,
    position_alerts,
    sector_rotation,
    longterm_watchlist,
    scan_date,
    portfolio_context: str = "",
) -> dict:
    """Determine trading mode, using deterministic path when possible."""
    with span("trading_mode_determination"):
        try:
            if early_mode in ("NORMAL", "LOW_CASH"):
                mode = {
                    "mode": early_mode,
                    "reason": f"Deployable cash: {deployable_cash:,.0f} VND",
                    "stagnant_positions": [],
                    "reallocation_targets": [],
                }
                print(f"  Mode: {early_mode} (deterministic, skipped LLM)", flush=True)
                return mode

            from agents import determine_trading_mode

            mode = await determine_trading_mode(
                deployable_cash=deployable_cash,
                position_alerts=position_alerts,
                sector_rotation=sector_rotation or {},
                longterm_watchlist=list(longterm_watchlist.keys()),
                scan_date=scan_date,
                portfolio_context=portfolio_context,
            )
            print(f"  Mode: {mode['mode']}", flush=True)
            print(f"  Reason: {mode['reason']}", flush=True)
            if mode.get("stagnant_positions"):
                print(f"  Stagnant: {', '.join(mode['stagnant_positions'])}", flush=True)
            return mode
        except Exception as e:
            report_caught("pipeline.helpers.trading_mode", e)
            raise RuntimeError(f"Trading mode phase failed: {e}") from e
