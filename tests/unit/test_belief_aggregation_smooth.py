"""SWI-122: smooth saturator + runtime-bound dissent floors.

The 2026-05-13 incident: 9/9 belief agents at Brier ≥ 0.60 received
identical down-weight, starving synthesis_picks. Plus prior cliff
regression (commit 73058107) where any agent above anchor lost ~98% of
weight regardless of marginal excess. The smooth exp saturator differentiates
without ever zeroing.
"""

from __future__ import annotations

import math

from agents.belief_aggregation._constants import (
    FALLBACK_BASE_RATES,
    current_dissent_thresholds,
    set_runtime_base_rates,
)
from agents.belief_aggregation._core import _sigmoid_weight_reduction


def test_smooth_saturator_differentiates_clustered_brier() -> None:
    """9 agents at brier ∈ [0.62, 0.66] must each receive a DIFFERENT weight,
    monotonically decreasing in brier, and none zeroed."""
    briers = [0.62, 0.63, 0.64, 0.65, 0.66, 0.62, 0.63, 0.64, 0.66]
    weights = [_sigmoid_weight_reduction(scored=30, brier=b) for b in briers]
    for w in weights:
        assert 0.10 <= w <= 0.95, f"weight {w} outside safe range"
    sorted_by_brier = sorted(zip(briers, weights, strict=False), key=lambda t: t[0])
    for (b1, w1), (b2, w2) in zip(sorted_by_brier, sorted_by_brier[1:], strict=False):
        if b1 < b2:
            assert w1 >= w2, f"non-monotonic: brier {b1} -> {w1} vs {b2} -> {w2}"


def test_smooth_saturator_never_zeroes_weight() -> None:
    """Even at extreme brier (well past the range saturation), weight stays
    above 0.15 — the asymptotic cap is 0.85 reduction (= 0.15 weight floor)."""
    weight = _sigmoid_weight_reduction(scored=100, brier=0.9)
    assert weight >= 0.15, f"smooth saturator zeroed weight at brier=0.9: {weight}"
    # Approaches cap but does NOT cross
    assert weight > 1.0 - 0.85


def test_brier_below_threshold_keeps_full_weight() -> None:
    weight = _sigmoid_weight_reduction(scored=30, brier=0.3)
    assert weight == 1.0


def test_cold_start_floor_keeps_full_weight_regardless_of_brier() -> None:
    weight = _sigmoid_weight_reduction(scored=5, brier=0.9)
    assert weight == 1.0


def test_runtime_dissent_floor_rebinds_on_base_rate_change() -> None:
    """``set_runtime_base_rates`` must rebind dissent floors so the
    runtime getters return anchor-derived values, NOT the module-load
    fallback."""
    original_bull_floor, _, original_agg_gate = current_dissent_thresholds()

    # Skewed rates push the uninformed Brier anchor higher
    new_rates = {"BULLISH": 0.1, "NEUTRAL": 0.1, "BEARISH": 0.8}
    try:
        set_runtime_base_rates(new_rates)
        rebound_bull_floor, _, rebound_agg_gate = current_dissent_thresholds()
        assert rebound_bull_floor != original_bull_floor or rebound_agg_gate != original_agg_gate
        # Floor still sits at 95% of new anchor
        from agents.belief_aggregation._anchors import uninformed_brier_anchor

        new_anchor = uninformed_brier_anchor(new_rates)
        assert math.isclose(rebound_bull_floor, round(0.95 * new_anchor, 4), abs_tol=1e-4)
    finally:
        set_runtime_base_rates(FALLBACK_BASE_RATES)
