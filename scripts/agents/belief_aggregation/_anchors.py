"""Normative anchors for belief-aggregation calibration policy.

SWI-122 / Fix 6: replaces snapshot-tuned thresholds with derivations from
a normative baseline. The aggregator's down-weight gate is "is this
agent worse than an uninformed forecaster who emits base rates verbatim"
— a 3-state Brier distribution on base rates p_bull/p_base/p_bear yields
``sum(p * (1 - p))``, ≈ 0.5 for near-uniform rates.

Free-floating snapshot constants (the prior 0.65 was tuned to
2026-04-14 data) drift the moment base rates shift. Anchoring the gate
to the live empirical base-rate Brier removes the snapshot dependency.
"""

from __future__ import annotations


def uninformed_brier_anchor(base_rates: dict[str, float]) -> float:
    """Brier score of a forecaster that emits base rates verbatim.

    For 3-state {BULLISH, NEUTRAL, BEARISH} probabilities summing to 1.0,
    the expected per-observation Brier is ``sum(p * (1 - p))``. This is
    the "no-skill" floor: any agent worse than this anchor is providing
    negative information and must be down-weighted.
    """
    return sum(p * (1 - p) for p in base_rates.values())
