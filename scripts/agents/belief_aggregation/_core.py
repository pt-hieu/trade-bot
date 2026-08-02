"""Conviction-weighted belief aggregation + base-rate anchoring.

Runs as post-processing after the aggregator LLM, before persistence.
Research: conviction-weighted aggregation beats simple averaging
(81.5% vs 79.1%, Going All-In); base-rate anchoring improves forecasts
by 23-43% (AI-Augmented Predictions, MIT/LSE 2024).
"""

from __future__ import annotations

import logging
import math

from agents.belief_models import derive_direction_from_probabilities

from ._constants import (
    _CALIBRATION_SIGMOID_MIDPOINT,
    _CALIBRATION_SIGMOID_SCALE,
    FALLBACK_BASE_RATES,
    MIN_SCORED_SOFT_FLOOR,
    current_brier_down_weight_threshold,
)
from ._dissent import preserve_high_conviction_dissent
from ._groups import group_calibration

logger = logging.getLogger(__name__)

# Distance above BRIER_DOWN_WEIGHT_THRESHOLD at which the graduated reduction
# saturates at full strength. SWI-122: tightened from 0.4 → 0.2 because the
# empirical Brier distribution post-2026-05-08 sits 0.18-0.20 above the
# anchor; the previous range failed to differentiate the cluster.
_BRIER_EXCESS_FULL_REDUCTION_RANGE = 0.2

# Smooth saturator parameters (SWI-122). The 0.85 cap is reached
# asymptotically — never the flat 1.0 cliff that commit 73058107 reverted.
_BRIER_REDUCTION_CAP = 0.85
_BRIER_SATURATOR_MIDPOINT = 0.5


def _effective_stats(agent_stats: dict) -> tuple[float, int]:
    """Prefer 30-day rolling brier — recovers after prompt fixes instead
    of staying poisoned by the all-time average. Uses default-on-missing
    semantics so brier=0.0 (pathological but explicit; downstream floor
    handles it) is not silently replaced with the 0.667 placeholder.
    """
    brier_30d = agent_stats.get("brier_30d")
    if brier_30d is not None:
        effective_brier = float(brier_30d)
    else:
        avg_brier = agent_stats.get("avg_brier")
        effective_brier = 0.667 if avg_brier is None else float(avg_brier)
    scored_raw = agent_stats.get("scored_beliefs")
    scored_beliefs = 0 if scored_raw is None else int(scored_raw)
    return effective_brier, scored_beliefs


def _sigmoid_weight_reduction(scored: int, brier: float) -> float:
    """Return the reduction factor in [0, 1] for a chronically poor agent.

    1.0 = no reduction. Three exempt mechanisms keep the factor at 1.0:

      * **Joint-group pooling** at ``_groups.py`` may share the brier
        of a peer group — handled upstream of this function.
      * **Cold-start floor** (``scored < MIN_SCORED_SOFT_FLOOR``):
        sample size too small for stable reduction.
      * **Aggregator-filter** at ``phase_beliefs.py:48`` is the third
        bypass mechanism — those agents never reach this function
        because they're filtered BEFORE aggregation runs. See
        ``shared/rules/belief_calibration_exemption.py``.

    Audit must distinguish these three when explaining "why agent X
    retains weight today" — the rule layer logs the path explicitly.
    """
    threshold = current_brier_down_weight_threshold()
    if scored < MIN_SCORED_SOFT_FLOOR or brier <= threshold:
        return 1.0
    sample_confidence = 1.0 / (
        1.0 + math.exp(-(scored - _CALIBRATION_SIGMOID_MIDPOINT) / _CALIBRATION_SIGMOID_SCALE)
    )
    brier_excess_factor = (brier - threshold) / _BRIER_EXCESS_FULL_REDUCTION_RANGE
    brier_excess_factor = max(0.0, min(1.0, brier_excess_factor))
    # SWI-122 smooth saturator: reduction(x) = cap * (1 - exp(-x/midpoint))
    # where x = brier_excess_factor * sample_confidence. Approaches but
    # never reaches _BRIER_REDUCTION_CAP — preventing the flat-cliff
    # regression that commit 73058107 reverted (sigmoid that zeroed every
    # agent above the anchor at scored>=18, starving synthesis_picks).
    raw = brier_excess_factor * sample_confidence
    reduction_amount = _BRIER_REDUCTION_CAP * (1.0 - math.exp(-raw / _BRIER_SATURATOR_MIDPOINT))
    # Fail loudly (CLAUDE.md) — survives ``python -O`` unlike `assert`.
    if not (0.0 <= reduction_amount <= _BRIER_REDUCTION_CAP):
        raise ValueError(f"brier reduction invariant breached: {reduction_amount}")
    return 1.0 - reduction_amount


def weighted_aggregate_beliefs_with_weights(
    analyst_beliefs: list[dict],
    calibration_stats: dict[str, dict] | None = None,
) -> tuple[dict, dict[str, float]]:
    """Conviction * accuracy_factor weighted aggregation plus per-agent weights.

    Each analyst's belief is weighted by `conviction * accuracy_factor`
    where `accuracy_factor = 1.0 / max(brier, 0.1) ** 2`. Joint-group
    calibration and graduated sigmoid reduction apply before the sum.

    Returns `(aggregated_result, per_agent_weights)`. The single-return
    counterpart `weighted_aggregate_beliefs` is a thin wrapper that keeps
    the callsite signature unchanged.
    """
    if not analyst_beliefs:
        return {}, {}

    calibration_stats = calibration_stats or {}
    weighted_bull = 0.0
    weighted_base = 0.0
    weighted_bear = 0.0
    total_weight = 0.0
    per_agent_weights: dict[str, float] = {}

    joint_overrides = group_calibration(calibration_stats)

    for belief in analyst_beliefs:
        # Use default-on-missing semantics (not `or`) — conviction=0.0 is a
        # valid explicit zero-weight signal that must not silently flip to 0.5.
        conviction_raw = belief.get("conviction")
        conviction = 0.5 if conviction_raw is None else float(conviction_raw)
        agent_key = belief.get("agent_key", "")

        effective_brier, scored_beliefs = _effective_stats(calibration_stats.get(agent_key) or {})
        accuracy_factor = 1.0 / max(effective_brier, 0.1) ** 2
        weight = conviction * accuracy_factor

        # Joint-group override applies before the sigmoid so pooled stats
        # drive the reduction when an entire ensemble is mis-calibrated.
        if agent_key in joint_overrides:
            effective_brier, scored_beliefs = joint_overrides[agent_key]

        reduction = _sigmoid_weight_reduction(scored_beliefs, effective_brier)
        if reduction < 1.0:
            pre_reduction = weight
            weight *= reduction
            log_level = logging.WARNING if reduction < 0.5 else logging.INFO
            logger.log(
                log_level,
                "Graduated weight reduction: %s brier=%.3f scored=%d "
                "reduction=%.2f weight %.3f → %.3f",
                agent_key,
                effective_brier,
                scored_beliefs,
                reduction,
                pre_reduction,
                weight,
            )

        logger.debug(
            "Belief weight: %s brier=%.3f scored=%d conv=%.2f weight=%.2f",
            agent_key,
            effective_brier,
            scored_beliefs,
            conviction,
            weight,
        )

        per_agent_weights[agent_key] = round(weight, 4)

        if weight == 0:
            continue

        weighted_bull += float(belief["bull_probability"]) * weight
        weighted_base += float(belief["base_probability"]) * weight
        weighted_bear += float(belief["bear_probability"]) * weight
        total_weight += weight

    if total_weight == 0:
        return (
            {
                "direction": "NEUTRAL",
                "bull_probability": FALLBACK_BASE_RATES["BULLISH"],
                "base_probability": FALLBACK_BASE_RATES["NEUTRAL"],
                "bear_probability": FALLBACK_BASE_RATES["BEARISH"],
            },
            per_agent_weights,
        )

    aggregated_bull = weighted_bull / total_weight
    aggregated_base = weighted_base / total_weight
    aggregated_bear = weighted_bear / total_weight

    aggregated_bull, aggregated_base, aggregated_bear = preserve_high_conviction_dissent(
        analyst_beliefs,
        aggregated_bull=aggregated_bull,
        aggregated_base=aggregated_base,
        aggregated_bear=aggregated_bear,
    )

    result = {
        "direction": derive_direction_from_probabilities(
            aggregated_bull, aggregated_base, aggregated_bear
        ),
        "bull_probability": round(aggregated_bull, 4),
        "base_probability": round(aggregated_base, 4),
        "bear_probability": round(aggregated_bear, 4),
    }
    return result, per_agent_weights


def weighted_aggregate_beliefs(
    analyst_beliefs: list[dict],
    calibration_stats: dict[str, dict] | None = None,
) -> dict:
    """Return only the aggregated result; drops the per-agent weight trace.

    Thin wrapper over :func:`weighted_aggregate_beliefs_with_weights` so
    the historical single-return signature stays available to existing
    callsites without duplicating the merge body.
    """
    result, _ = weighted_aggregate_beliefs_with_weights(analyst_beliefs, calibration_stats)
    return result


def anchor_aggregated_belief(
    aggregated: dict,
    base_rates: dict | None = None,
    anchor_weight: float = 0.1,
) -> dict:
    """Blend an aggregated belief 90% toward the weighted output, 10% toward base rates.

    Apply AFTER `weighted_aggregate_beliefs` — anchoring sub-agent inputs
    would destructively pull bull_probability below
    DISSENT_PRESERVATION_BULL_FLOOR and silently no-op the preservation rule.
    """
    base_rates = base_rates or FALLBACK_BASE_RATES
    anchored_bull = round(
        (1 - anchor_weight) * float(aggregated["bull_probability"])
        + anchor_weight * base_rates["BULLISH"],
        4,
    )
    anchored_base = round(
        (1 - anchor_weight) * float(aggregated["base_probability"])
        + anchor_weight * base_rates["NEUTRAL"],
        4,
    )
    anchored_bear = round(
        (1 - anchor_weight) * float(aggregated["bear_probability"])
        + anchor_weight * base_rates["BEARISH"],
        4,
    )
    return {
        **aggregated,
        "bull_probability": anchored_bull,
        "base_probability": anchored_base,
        "bear_probability": anchored_bear,
        "direction": derive_direction_from_probabilities(
            anchored_bull, anchored_base, anchored_bear
        ),
    }


def apply_base_rate_anchor(
    beliefs: list[dict],
    base_rates: dict | None = None,
    anchor_weight: float = 0.1,
) -> list[dict]:
    """Blend a list of beliefs in place toward base rates."""
    base_rates = base_rates or FALLBACK_BASE_RATES
    for belief in beliefs:
        anchored = anchor_aggregated_belief(
            belief, base_rates=base_rates, anchor_weight=anchor_weight
        )
        belief["bull_probability"] = anchored["bull_probability"]
        belief["base_probability"] = anchored["base_probability"]
        belief["bear_probability"] = anchored["bear_probability"]
    return beliefs
