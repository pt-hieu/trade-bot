"""Phase 2 §2.5 — distinguish 3 calibration-bypass mechanisms.

  1. Aggregator double-counting filter (pre-aggregation; never reaches sigmoid)
  2. Brier sigmoid (≤ 0.65 retains full weight)
  3. Cold-start floor (scored < 18 retains full weight)

The fixture in case 6 uses live numbers from
``v_agent_belief_accuracy`` for sector_technical (audited 2026-04-29):
brier_30d=0.630, scored_beliefs >= 18 → retains weight via brier
threshold (mechanism 2), NOT cold-start.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from agents.belief_aggregation._constants import (  # noqa: E402
    BRIER_DOWN_WEIGHT_THRESHOLD,
    MIN_SCORED_SOFT_FLOOR,
)
from agents.belief_aggregation._core import _sigmoid_weight_reduction  # noqa: E402
from shared.rules.belief_calibration_exemption import (  # noqa: E402
    aggregator_keys,
    is_aggregator_double_counter,
)


class TestAggregatorFilter:
    """Mechanism 1 — pre-aggregation filter."""

    def test_sector_aggregator_filtered(self) -> None:
        assert is_aggregator_double_counter("sector_aggregator")

    def test_positions_aggregator_filtered(self) -> None:
        assert is_aggregator_double_counter("positions_aggregator")

    def test_deterministic_aggregator_not_filtered(self) -> None:
        # `deterministic_aggregator` is the OUTPUT row produced AT
        # phase_beliefs.py:142, not an input. It never appears in the
        # filtered_beliefs loop. Filter says "not aggregator" because
        # the YAML doesn't have ensemble_role: aggregator (no YAML at all).
        assert not is_aggregator_double_counter("deterministic_aggregator")

    def test_sub_agent_not_filtered(self) -> None:
        assert not is_aggregator_double_counter("sector_technical")
        assert not is_aggregator_double_counter("positions_value")

    def test_aggregator_keys_subset_check(self) -> None:
        keys = aggregator_keys()
        assert "sector_aggregator" in keys
        assert "positions_aggregator" in keys
        # Sub-agents must NOT be in the aggregator allowlist.
        assert "sector_technical" not in keys


class TestSigmoidThreshold:
    """Mechanism 2 — brier <= uninformed-anchor retains full weight.

    SWI-122 / Fix 6: threshold is now the uninformed-forecaster Brier
    anchor (~0.47 for FALLBACK_BASE_RATES), down from the
    snapshot-tuned 0.65. Agents above that anchor are providing
    negative information vs emitting base rates verbatim.
    """

    def test_brier_well_below_anchor_full_weight(self) -> None:
        # brier=0.30 << anchor (~0.47), scored=50 → full weight.
        assert _sigmoid_weight_reduction(50, 0.30) == 1.0

    def test_brier_at_threshold_inclusive_full_weight(self) -> None:
        assert _sigmoid_weight_reduction(50, BRIER_DOWN_WEIGHT_THRESHOLD) == 1.0

    def test_brier_above_anchor_with_high_scored_reduces(self) -> None:
        # brier=0.80, scored=50 → sigmoid reduces (brier > anchor).
        weight = _sigmoid_weight_reduction(50, 0.80)
        assert weight < 0.5

    def test_positions_technical_april_2026_actual_metrics(self) -> None:
        """SWI-122 / Fix 6 regression: positions_technical brier_30d=0.6469
        with scored=56 must now down-weight (was full-weight under the
        snapshot 0.65 threshold). Today (2026-04-29) all 9 belief agents
        had Brier worse than coin-flip 0.5, so the previous threshold
        produced 0 down-weights — exactly the bug Fix 6 closes."""
        weight = _sigmoid_weight_reduction(scored=56, brier=0.6469)
        assert weight < 1.0


class TestColdStartFloor:
    """Mechanism 3 — scored < 18 retains full weight regardless of brier."""

    def test_cold_start_with_high_brier_retains_weight(self) -> None:
        # brier=0.99, scored=10 → mechanism 3 (cold-start).
        assert _sigmoid_weight_reduction(10, 0.99) == 1.0

    def test_cold_start_boundary_below(self) -> None:
        assert _sigmoid_weight_reduction(MIN_SCORED_SOFT_FLOOR - 1, 0.99) == 1.0

    def test_above_cold_start_with_high_brier_reduces(self) -> None:
        # scored=18 boundary AT floor: returns 1.0 only because brier>0.65
        # AND scored>=18 path; at scored exactly 18 mid-range, sigmoid
        # midpoint produces ~0.5 reduction. The cold-start guard fires
        # only when scored < MIN_SCORED_SOFT_FLOOR.
        weight = _sigmoid_weight_reduction(MIN_SCORED_SOFT_FLOOR, 0.99)
        # Past cold-start floor, brier > 0.65 → reduction kicks in.
        assert weight < 1.0


class TestGraduatedBrierExcessCurve:
    """SWI-262 / SWI-122 — graduated reduction must differentiate marginal
    from catastrophic Brier WITHOUT zeroing any agent. The smooth saturator
    asymptotes at the 0.85 reduction cap (= 0.15 weight floor); past that
    point the curve never crosses zero.
    """

    def test_brier_marginally_above_anchor_keeps_partial_weight(self) -> None:
        # 2026-05-06 sector_news reproducer: brier=0.605, scored=628.
        # Range tightened to 0.2 (SWI-122) so this point now sits deeper
        # in the saturator — still well above the 0.15 weight floor.
        weight = _sigmoid_weight_reduction(scored=628, brier=0.605)
        assert 0.30 <= weight <= 0.60, f"expected partial-weight curve point, got {weight}"

    def test_brier_far_above_anchor_with_large_scored_reduces_heavily(self) -> None:
        # SWI-122: smooth saturator asymptotes at 0.85 reduction; weight
        # floor is 0.15. Test pins the floor end of the curve without
        # demanding the impossible zero-out the old flat-cliff produced.
        weight = _sigmoid_weight_reduction(scored=200, brier=0.90)
        assert 0.15 <= weight <= 0.30, f"smooth saturator floor breached, got {weight}"


@pytest.mark.parametrize(
    "brier,scored,expected_min,expected_max",
    [
        (0.605, 628, 0.30, 0.60),
        (0.75, 100, 0.15, 0.40),
        (0.90, 200, 0.15, 0.30),
    ],
)
def test_sigmoid_weight_reduction_curve_pinned(
    brier: float, scored: int, expected_min: float, expected_max: float
) -> None:
    """Curve-pinning regression: any future revert that flattens the
    graduated formula breaks this test before reaching production."""
    result = _sigmoid_weight_reduction(scored=scored, brier=brier)
    assert expected_min <= result <= expected_max, (
        f"brier={brier} scored={scored} → weight={result} "
        f"(expected [{expected_min}, {expected_max}])"
    )


class TestMechanismDistinction:
    """Cross-cutting: ensure the three mechanisms are reported distinctly."""

    def test_brier_low_reason_not_cold_start(self) -> None:
        # brier=0.30 << anchor → mechanism 2 retains weight, not cold-start.
        weight = _sigmoid_weight_reduction(50, 0.30)
        assert weight == 1.0
        assert MIN_SCORED_SOFT_FLOOR <= 50
        assert BRIER_DOWN_WEIGHT_THRESHOLD >= 0.30

    def test_aggregator_never_reaches_sigmoid(self) -> None:
        # Mechanism 1 fires upstream — the agent never appears in the
        # `filtered_beliefs` loop, so its brier/scored never reach this
        # function. The structured allowlist is the audit citation.
        for agent_key in aggregator_keys():
            assert is_aggregator_double_counter(agent_key)
