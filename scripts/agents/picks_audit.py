"""Per-candidate score-audit helpers for the BUY-recommendation framework.

Phase A wiring (SWI-171). Lifted out of ``picks.py`` so the scoring
side-store + audit-row plumbing don't push the main pick-extraction
module past its 300-line cap.

The function :func:`build_score_inputs` extracts the 12 raw features
used by ``shared.rules.scoring.compute_score`` from the pieces a picks
loop already has on hand (``signal``, ``tech_data``, ``setup``,
``strategy_cls``, ``simulation``, ``belief``). Missing inputs map to
neutral values so a setup_invalid drop scores 0 cleanly without
crashing.

:func:`audit_layer_drop` is the thin wrapper picks.py / picks_exit_dispatch
call at each rejection layer — it computes the score with current-state
features, persists the row via :class:`ScoreRecorder`, and returns the
score so the caller can also use it for in-run logging.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from shared.neon._utils import safe_float
from shared.rules.exit_strategy import derive_atr_trail_synthetic_rr
from shared.rules.scoring import (
    GatedBy,
    ReliefContext,
    ScoreInputs,
    ScoreResult,
    ScoringPhase,
    compute_score,
)

from .belief_mapping import map_signal_confidence_to_conviction

if TYPE_CHECKING:
    from eval.score_recorder import ScoreRecorder

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditRunContext:
    """Run-level audit state — built once per ``extract_top_picks`` call.

    Carries the suppressor-predicate inputs that are stable across the
    pick loop (regime, sector belief totals, shock flag, macro relief)
    plus the recorder + phase identity. Per-candidate state (ticker,
    sector, R:R, per-ticker positive catalyst) is passed separately to
    :func:`audit_layer_drop`.
    """

    recorder: ScoreRecorder | None
    phase: ScoringPhase
    regime: str
    urgency_tier: str | None
    underlying_stress: bool
    shock_active: bool
    has_high_positive_macro_catalyst: bool
    bullish_sector_belief_count: int
    total_sector_count: int


def _strategy_confidence(strategy_cls: object | None) -> float:
    """Read classify_strategy().confidence as a [0,1] feature."""
    if strategy_cls is None:
        return 0.0
    confidence = getattr(strategy_cls, "confidence", None)
    if confidence is None:
        return 0.0
    return max(0.0, min(1.0, safe_float(confidence, 0.0) or 0.0))


def _catalyst_strength(
    ticker: str,
    boosted: set[str] | frozenset[str] | None,
    high_positive_count: dict[str, int] | None,
) -> float:
    """HIGH_POSITIVE=1.0 when the ticker is boosted AND has a high-positive
    catalyst row; otherwise MEDIUM=0.6 when boosted only; else 0."""
    if not boosted or ticker.upper() not in boosted:
        return 0.0
    if high_positive_count and high_positive_count.get(ticker.upper(), 0) > 0:
        return 1.0
    return 0.6


def _trend_alignment(tech_data: dict | None) -> str:
    """Map tech_data.trend.trend label to UPTREND/SIDEWAYS/DOWNTREND/UNKNOWN."""
    if not tech_data:
        return "UNKNOWN"
    trend = tech_data.get("trend") or {}
    label = (trend.get("trend") or "").upper()
    if label in ("UPTREND", "SIDEWAYS", "DOWNTREND"):
        return label
    return "UNKNOWN"


def build_score_inputs(
    *,
    signal: dict,
    tech_data: dict | None,
    setup: dict | None,
    strategy_cls: object | None = None,
    simulation: object | None = None,
    belief: dict | None = None,
    boosted: set[str] | frozenset[str] | None = None,
    high_positive_count: dict[str, int] | None = None,
    bullish_sector_belief_count: int = 0,
    total_sector_count: int = 0,
    trend_gate_failed: bool = False,
) -> ScoreInputs:
    """Pack what the picks loop currently has into :class:`ScoreInputs`.

    Missing fields are filled with deterministic neutral values so the
    same candidate produces the same score whether scored at layer 1
    (setup_invalid → R:R=0) or layer 5 (full).

    ``trend_gate_failed=True`` zeroes the ``trend_alignment`` feature so
    the score row written at the layer-2 drop point reflects the gate's
    verdict (per plan: "score reflects all features INCLUDING
    trend_alignment=0").
    """
    ticker = (signal.get("ticker") or "").upper()
    setup = setup or {}
    if not setup.get("valid"):
        risk_reward = 0.0
    elif setup.get("exit_family") == "ATR_TRAIL":
        # ATR_TRAIL setups carry setup["risk_reward"]=None (load-bearing
        # for downstream null-target consumers); the synthetic helper
        # produces a scoring-only R:R that never writes back to setup.
        risk_reward = derive_atr_trail_synthetic_rr(
            entry=setup.get("entry"),
            stop=setup.get("stop"),
            atr=(tech_data or {}).get("atr"),
        )
    else:
        risk_reward = safe_float(setup.get("risk_reward"), 0.0) or 0.0
    flow = (tech_data or {}).get("flow") or {}
    volume = setup.get("volume_vs_avg")
    if volume is None:
        volume = (tech_data or {}).get("volume_vs_avg")

    inputs: ScoreInputs = {
        "risk_reward": risk_reward,
        "sim_p_target": safe_float(getattr(simulation, "p_target", None), 0.0) or 0.0,
        "sim_p_stop": safe_float(getattr(simulation, "p_stop", None), 0.5) or 0.5,
        "sim_ev": safe_float(getattr(simulation, "expected_return_pct", None), 0.0) or 0.0,
        "strategy_confidence": _strategy_confidence(strategy_cls),
        "belief_conviction": map_signal_confidence_to_conviction(signal.get("confidence"), belief),
        "catalyst_strength": _catalyst_strength(ticker, boosted, high_positive_count),
        "bullish_sector_belief_count": int(bullish_sector_belief_count),
        "total_sector_count": int(total_sector_count),
        "rs_20d": safe_float((tech_data or {}).get("rs_20d"), 1.0) or 1.0,
        "volume_vs_avg": safe_float(volume, 0.0) or 0.0,
        "trend_alignment": "DOWNTREND" if trend_gate_failed else _trend_alignment(tech_data),
        "foreign_net_strength": safe_float(flow.get("foreign_net"), 0.0) or 0.0,
    }
    return inputs


def build_relief_context(
    *,
    underlying_stress: bool,
    shock_active: bool,
    has_high_positive_macro_catalyst: bool,
    has_candidate_positive_catalyst: bool,
    bullish_sector_belief_count: int,
    candidate_risk_reward: float,
) -> ReliefContext:
    """Pack composer Rule 5a inputs into :class:`ReliefContext`."""
    return {
        "underlying_stress": bool(underlying_stress),
        "shock_active": bool(shock_active),
        "has_high_positive_macro_catalyst": bool(has_high_positive_macro_catalyst),
        "has_candidate_positive_catalyst": bool(has_candidate_positive_catalyst),
        "bullish_sector_belief_count": int(bullish_sector_belief_count),
        "candidate_risk_reward": float(candidate_risk_reward or 0.0),
    }


async def audit_candidate(
    *,
    recorder: ScoreRecorder | None,
    ticker: str,
    phase: ScoringPhase,
    features: ScoreInputs,
    regime: str,
    relief_context: ReliefContext | None,
    shock_active: bool,
    gated_by: GatedBy,
    gate_reason: str | None,
    sector: str | None,
    source: str,
    urgency_tier: str | None,
    sim_populated: bool = False,
) -> ScoreResult | None:
    """Compute score from current features and persist via the recorder.

    Returns the :class:`ScoreResult` so callers can also log/diagnose
    in-run. When ``recorder`` is None (e.g. unit-test calls without a
    pipeline), the function still computes the score and returns it but
    skips persistence.
    """
    result = compute_score(
        features=features,
        regime=regime,
        relief_context=relief_context,
        shock_active=shock_active,
        sim_populated=sim_populated,
    )
    if recorder is not None:
        await recorder.record(
            ticker=ticker,
            phase=phase,
            result=result,
            gated_by=gated_by,
            gate_reason=gate_reason,
            regime=regime,
            sector=sector,
            source=source,
            urgency_tier=urgency_tier,
            feature_values=dict(features),
        )
    return result


async def audit_layer_drop(
    *,
    ctx: AuditRunContext,
    ticker: str,
    sector_label: str | None,
    candidate_source: str,
    per_ticker_positive: bool,
    features: ScoreInputs,
    gated_by: GatedBy,
    gate_reason: str | None,
    chosen_rr_for_relief: float,
    sim_populated: bool = False,
) -> ScoreResult | None:
    """Single seam for the picks-loop layer-drop audit pattern.

    Replaces the per-iteration closure that pyright/ruff flagged as a
    loop-variable-binding hazard (B023). Builds the relief context from
    the run-level :class:`AuditRunContext` + the per-candidate signals,
    computes the score, and persists the audit row.
    """
    relief = build_relief_context(
        underlying_stress=ctx.underlying_stress,
        shock_active=ctx.shock_active,
        has_high_positive_macro_catalyst=ctx.has_high_positive_macro_catalyst,
        has_candidate_positive_catalyst=per_ticker_positive,
        bullish_sector_belief_count=ctx.bullish_sector_belief_count,
        candidate_risk_reward=chosen_rr_for_relief,
    )
    return await audit_candidate(
        recorder=ctx.recorder,
        ticker=ticker,
        phase=ctx.phase,
        features=features,
        regime=ctx.regime,
        relief_context=relief,
        shock_active=ctx.shock_active,
        gated_by=gated_by,
        gate_reason=gate_reason,
        sector=sector_label,
        source=candidate_source,
        urgency_tier=ctx.urgency_tier,
        sim_populated=sim_populated,
    )


__all__ = [
    "AuditRunContext",
    "audit_candidate",
    "audit_layer_drop",
    "build_relief_context",
    "build_score_inputs",
]
