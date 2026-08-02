"""Coverage for check_candidate_gate — DEF-005 per-candidate gate.

The gate is pure; tests poke each rejection path plus the catalyst-aware
effective floor. SHOCK_FLOOR_MINIMUM_RR clamp is verified when a catalyst
adjustment would otherwise dip below 2.5. No adjustment → morning parity.
"""

from __future__ import annotations

from shared.rules.entry_gates import SHOCK_FLOOR_MINIMUM_RR, check_candidate_gate


def _setup(
    *,
    valid: bool = True,
    risk_reward: float = 3.2,
    position_vnd: int = 5_000_000,
    error: str | None = None,
) -> dict:
    setup: dict = {
        "valid": valid,
        "risk_reward": risk_reward,
        "position_vnd": position_vnd,
    }
    if error:
        setup["error"] = error
    return setup


class TestCandidateGatePassingPaths:
    def test_rr_above_floor_passes(self) -> None:
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=3.2),
            rr_floor=3.0,
            sizing_floor_vnd=0,
        )
        assert result["passed"] is True
        assert result["reason"] is None
        assert result["effective_rr_floor"] == 3.0

    def test_rr_equal_to_floor_passes(self) -> None:
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=3.0),
            rr_floor=3.0,
            sizing_floor_vnd=0,
        )
        assert result["passed"] is True


class TestCandidateGateRejectionPaths:
    def test_invalid_setup_rejects(self) -> None:
        result = check_candidate_gate(
            trade_setup=_setup(valid=False, error="missing levels"),
            rr_floor=3.0,
            sizing_floor_vnd=0,
        )
        assert result["passed"] is False
        assert "setup_invalid" in (result["reason"] or "")
        assert "missing levels" in (result["reason"] or "")

    def test_rr_just_below_floor_rejects(self) -> None:
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=2.99),
            rr_floor=3.0,
            sizing_floor_vnd=0,
        )
        assert result["passed"] is False
        assert "rr_below_floor" in (result["reason"] or "")

    def test_sizing_below_floor_rejects(self) -> None:
        result = check_candidate_gate(
            trade_setup=_setup(position_vnd=100_000),
            rr_floor=3.0,
            sizing_floor_vnd=500_000,
        )
        assert result["passed"] is False
        assert "position_below_sizing_floor" in (result["reason"] or "")

    def test_sizing_floor_zero_skipped(self) -> None:
        # A zero sizing floor must not reject a tiny position — morning
        # callers depend on this to preserve behavior.
        result = check_candidate_gate(
            trade_setup=_setup(position_vnd=1_000),
            rr_floor=3.0,
            sizing_floor_vnd=0,
        )
        assert result["passed"] is True


class TestCandidateGateCatalystAdjustment:
    def test_high_positive_adjustment_lowers_effective_floor(self) -> None:
        # Non-shock regime: floor 3.0 - 0.5 = 2.5 (matches SHOCK_FLOOR_MINIMUM_RR
        # which is also the effective clamp; both mean the same number here).
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=2.6),
            rr_floor=3.0,
            sizing_floor_vnd=0,
            catalyst_rr_adjustment=0.5,
        )
        assert result["passed"] is True
        assert result["effective_rr_floor"] == 2.5

    def test_medium_positive_quarter_point_discount(self) -> None:
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=2.8),
            rr_floor=3.0,
            sizing_floor_vnd=0,
            catalyst_rr_adjustment=0.25,
        )
        assert result["passed"] is True
        assert result["effective_rr_floor"] == 2.75

    def test_shock_floor_minimum_clamps_adjustment(self) -> None:
        # Shock regime 4.0 floor with 0.5 discount → effective 3.5.
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=3.6),
            rr_floor=4.0,
            sizing_floor_vnd=0,
            catalyst_rr_adjustment=0.5,
        )
        assert result["passed"] is True
        assert result["effective_rr_floor"] == 3.5

    def test_shock_floor_minimum_never_underruns_safety(self) -> None:
        # Pathological case: tiny regime floor + huge catalyst discount —
        # clamp enforces SHOCK_FLOOR_MINIMUM_RR (2.5) as hard minimum.
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=2.4),
            rr_floor=2.0,
            sizing_floor_vnd=0,
            catalyst_rr_adjustment=2.0,
        )
        assert result["passed"] is False
        assert result["effective_rr_floor"] == SHOCK_FLOOR_MINIMUM_RR

    def test_zero_adjustment_preserves_morning_behavior(self) -> None:
        # Morning invariants: rr_floor=2.0 and adjustment=0 must behave
        # exactly like the legacy inline chosen_rr < min_rr check. No clamp
        # applies to the floor when adjustment is zero.
        passing = check_candidate_gate(
            trade_setup=_setup(risk_reward=2.0),
            rr_floor=2.0,
            sizing_floor_vnd=0,
        )
        failing = check_candidate_gate(
            trade_setup=_setup(risk_reward=1.99),
            rr_floor=2.0,
            sizing_floor_vnd=0,
        )
        assert passing["passed"] is True
        assert passing["effective_rr_floor"] == 2.0
        assert failing["passed"] is False
        assert failing["effective_rr_floor"] == 2.0

    def test_negative_adjustment_treated_as_zero(self) -> None:
        # Defensive: NEGATIVE catalyst adjustments must not raise the floor.
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=3.0),
            rr_floor=3.0,
            sizing_floor_vnd=0,
            catalyst_rr_adjustment=-0.5,
        )
        assert result["passed"] is True
        assert result["effective_rr_floor"] == 3.0


class TestStackedShockRelief:
    """L2 (2026-04-27): per-ticker stacked-shock relief — caps R:R floor at
    3.0 + sizing × 0.75 when caller's per-ticker compute matches. Other
    candidates same day pass the unmodified floor — no fleet leak."""

    def test_relief_caps_rr_floor_at_three(self) -> None:
        # Stressed regime 4.0 floor + relief flag → cap at 3.0.
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=3.0),
            rr_floor=4.0,
            sizing_floor_vnd=0,
            stacked_shock_relief=True,
        )
        assert result["passed"] is True
        assert result["effective_rr_floor"] == 3.0

    def test_relief_off_keeps_legacy_floor(self) -> None:
        # No stacked-shock relief → unchanged 4.0 floor; 3.0 R:R rejects.
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=3.0),
            rr_floor=4.0,
            sizing_floor_vnd=0,
            stacked_shock_relief=False,
        )
        assert result["passed"] is False
        assert result["effective_rr_floor"] == 4.0
        assert "rr_below_floor" in (result["reason"] or "")

    def test_relief_with_sizing_floor_applies_multiplier(self) -> None:
        # Sizing floor 1_000_000 × 0.75 = 750_000 — a 760_000 position
        # passes; at 700_000 it rejects.
        passing = check_candidate_gate(
            trade_setup=_setup(risk_reward=3.5, position_vnd=760_000),
            rr_floor=3.5,
            sizing_floor_vnd=1_000_000,
            stacked_shock_relief=True,
        )
        rejecting = check_candidate_gate(
            trade_setup=_setup(risk_reward=3.5, position_vnd=700_000),
            rr_floor=3.5,
            sizing_floor_vnd=1_000_000,
            stacked_shock_relief=True,
        )
        assert passing["passed"] is True
        assert rejecting["passed"] is False
        # Reason text reports the effective (post-multiplier) floor for clarity.
        assert "750000" in (rejecting["reason"] or "")

    def test_relief_no_sizing_floor_path(self) -> None:
        # Morning callsite uses sizing_floor_vnd=0 — multiplier path
        # short-circuits, only the R:R cap applies.
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=3.0, position_vnd=1_000),
            rr_floor=4.0,
            sizing_floor_vnd=0,
            stacked_shock_relief=True,
        )
        assert result["passed"] is True
        assert result["effective_rr_floor"] == 3.0

    def test_relief_does_not_raise_floor_below_cap(self) -> None:
        # If the floor is already below the cap (e.g. 2.5 calm regime),
        # min() leaves it alone — relief never raises a low floor.
        result = check_candidate_gate(
            trade_setup=_setup(risk_reward=2.5),
            rr_floor=2.5,
            sizing_floor_vnd=0,
            stacked_shock_relief=True,
        )
        assert result["passed"] is True
        assert result["effective_rr_floor"] == 2.5
