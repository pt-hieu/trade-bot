"""Dissent preservation for weighted belief aggregation.

When one sub-agent holds a high-conviction directional view but the
weighted mean washes to the middle (<0.40 = NEUTRAL gate), lift the
aggregated probability toward that sub-agent's value instead of letting
the dissent get averaged away.
"""

from __future__ import annotations

import logging

from ._constants import (
    DISSENT_PRESERVATION_RELAX,
    current_dissent_thresholds,
)

logger = logging.getLogger(__name__)


def _lift_and_renormalize(
    *,
    lifted_value: float,
    current_value: float,
    other_a: float,
    other_b: float,
) -> tuple[float, float, float]:
    """Lift one probability to `lifted_value`; scale the other two so the
    three still sum to ~1.0. The other_a:other_b ratio is preserved.
    """
    if lifted_value <= current_value or current_value >= 1.0:
        return current_value, other_a, other_b
    scale = (1.0 - lifted_value) / (1.0 - current_value)
    return lifted_value, other_a * scale, other_b * scale


def preserve_high_conviction_dissent(
    analyst_beliefs: list[dict],
    *,
    aggregated_bull: float,
    aggregated_base: float,
    aggregated_bear: float,
) -> tuple[float, float, float]:
    """Lift aggregated probabilities toward a high-conviction dissenter
    when the weighted mean fell below the NEUTRAL gate. Runs before
    base-rate anchoring so the anchor still nudges the preserved value.
    """
    # Gate semantic: "are we already directional?" — base is NEUTRAL,
    # not a direction, so exclude it from the directional max check.
    # Before fix (2026-04-15 pipeline review, MON-2026-04-13-003): base-heavy
    # distributions (e.g. bull=0.398, base=0.452, bear=0.15 on DXS after
    # sector_enrichment's sigmoid reduction) short-circuited preservation
    # and collapsed to NEUTRAL because argmax=base even though a strong
    # bull dissenter was present.
    # Read runtime-bound floors so set_runtime_base_rates() takes effect
    # without a module reload (SWI-122). One getter for all three keeps
    # the values in lock-step under rate rebinds.
    bull_floor, conv_floor, agg_gate = current_dissent_thresholds()

    max_directional = max(aggregated_bull, aggregated_bear)
    if max_directional >= agg_gate:
        return aggregated_bull, aggregated_base, aggregated_bear

    bull_dissenter: dict | None = None
    bull_strength = 0.0
    bear_dissenter: dict | None = None
    bear_strength = 0.0
    for belief in analyst_beliefs:
        conviction = float(belief.get("conviction") or 0)
        if conviction < conv_floor:
            continue
        bull_p = float(belief.get("bull_probability") or 0)
        if bull_p >= bull_floor and bull_p > bull_strength:
            bull_dissenter = belief
            bull_strength = bull_p
        bear_p = float(belief.get("bear_probability") or 0)
        if bear_p >= bull_floor and bear_p > bear_strength:
            bear_dissenter = belief
            bear_strength = bear_p

    # Both sides dissenting = 3-way split; keep only the stronger signal.
    lift_bull = bull_dissenter is not None and (
        bear_dissenter is None or bull_strength >= bear_strength
    )
    lift_bear = bear_dissenter is not None and not lift_bull

    if lift_bull and bull_dissenter is not None:
        preserved = max(aggregated_bull, bull_strength - DISSENT_PRESERVATION_RELAX)
        new_bull, new_base, new_bear = _lift_and_renormalize(
            lifted_value=preserved,
            current_value=aggregated_bull,
            other_a=aggregated_base,
            other_b=aggregated_bear,
        )
        if new_bull != aggregated_bull:
            logger.info(
                "dissent_preservation(bull): %.3f -> %.3f (dissenter=%s bull=%.3f)",
                aggregated_bull,
                new_bull,
                bull_dissenter.get("agent_key", "?"),
                bull_strength,
            )
        return new_bull, new_base, new_bear

    if lift_bear and bear_dissenter is not None:
        preserved = max(aggregated_bear, bear_strength - DISSENT_PRESERVATION_RELAX)
        new_bear, new_base, new_bull = _lift_and_renormalize(
            lifted_value=preserved,
            current_value=aggregated_bear,
            other_a=aggregated_base,
            other_b=aggregated_bull,
        )
        if new_bear != aggregated_bear:
            logger.info(
                "dissent_preservation(bear): %.3f -> %.3f (dissenter=%s bear=%.3f)",
                aggregated_bear,
                new_bear,
                bear_dissenter.get("agent_key", "?"),
                bear_strength,
            )
        return new_bull, new_base, new_bear

    return aggregated_bull, aggregated_base, aggregated_bear
