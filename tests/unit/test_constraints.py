"""Tests for shared/rules/constraints.py — centralized constraint logic."""

from datetime import date
from unittest.mock import patch

import pytest

from shared.rules.constraints import (
    PipelineConstraints,
    apply_circuit_breakers,
    calculate_goal_urgency,
    compose_with_retro,
    compute_directive_constraints,
    compute_goal_metrics,
    inject_entry_gate,
    is_long_horizon_goal,
)

ASSESS_REACHABILITY_PATH = "shared.rules.constraints.assess_reachability"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_goal(
    *,
    target: float = 20_000_000,
    realized: float = 5_000_000,
    start_date: str = "2026-01-01",
    deadline: str = "2026-04-10",
    goal_type: str = "Monthly",
    name: str = "Test Goal",
) -> dict:
    return {
        "name": name,
        "goal_type": goal_type,
        "target": target,
        "realized": realized,
        "start_date": start_date,
        "deadline": deadline,
    }


def _make_cash(deployable: int = 20_000_000) -> dict:
    return {"deployable": deployable}


# ---------------------------------------------------------------------------
# calculate_goal_urgency
# ---------------------------------------------------------------------------


class TestCalculateGoalUrgency:
    """Urgency tier from (on_track, days_left) → tier + constraints."""

    def test_on_track_returns_normal(self):
        result = calculate_goal_urgency(on_track=True, days_left=20)
        assert result["urgency"] == "NORMAL"
        assert result["min_rr"] == 2.5
        assert result["max_picks"] == 3

    @pytest.mark.parametrize(
        ("days_left", "expected_urgency"),
        [
            (20, "AWARENESS"),
            (16, "AWARENESS"),
        ],
    )
    def test_behind_many_days_awareness(self, days_left: int, expected_urgency: str):
        result = calculate_goal_urgency(on_track=False, days_left=days_left)
        assert result["urgency"] == expected_urgency

    def test_elevated_tier_days_12(self):
        result = calculate_goal_urgency(on_track=False, days_left=12)
        assert result["urgency"] == "ELEVATED"
        assert result["min_rr"] == 2.3

    @pytest.mark.parametrize("days_left", [11, 12, 15])
    def test_elevated_tier_range(self, days_left: int):
        result = calculate_goal_urgency(on_track=False, days_left=days_left)
        assert result["urgency"] == "ELEVATED"

    def test_high_tier_days_7(self):
        result = calculate_goal_urgency(on_track=False, days_left=7)
        assert result["urgency"] == "HIGH"
        assert result["min_rr"] == 2.0

    def test_acceptance_tier_days_3(self):
        result = calculate_goal_urgency(on_track=False, days_left=3)
        assert result["urgency"] == "ACCEPTANCE"
        assert result["min_rr"] == 2.0
        assert result["max_picks"] == 3


# ---------------------------------------------------------------------------
# compute_goal_metrics — on_track determination with scan_date
# ---------------------------------------------------------------------------


class TestComputeGoalMetricsOnTrack:
    """on_track logic uses scan_date and start_date for deterministic calculation."""

    def test_7_percent_progress_with_87_percent_time_elapsed_is_behind(self):
        """Realistic scenario: 7.4% progress, 87% time elapsed → on_track=False."""
        # elapsed: 2026-01-29 to 2026-04-01 = 62 days out of 71 total (87%)
        # realized=2.96M out of 40M target = 7.4% — far below 87%*70% threshold
        goal = _make_goal(
            target=20_000_000,
            realized=2_960_000,
            start_date="2026-01-29",
            deadline="2026-04-10",
        )
        with patch(ASSESS_REACHABILITY_PATH, return_value=(None, "")):
            result = compute_goal_metrics(
                goal,
                deployable=55_000_000,
                scan_date=date(2026, 4, 1),
                format_prose=False,
            )
        assert result["on_track"] is False

    def test_goal_just_started_elapsed_zero_is_on_track(self):
        """elapsed_days <= 0 → always on_track=True (goal just started)."""
        goal = _make_goal(
            target=20_000_000,
            realized=0,
            start_date="2026-04-01",
            deadline="2026-04-30",
        )
        with patch(ASSESS_REACHABILITY_PATH, return_value=(None, "")):
            result = compute_goal_metrics(
                goal,
                deployable=55_000_000,
                scan_date=date(2026, 4, 1),
                format_prose=False,
            )
        assert result["on_track"] is True

    def test_negative_realized_always_behind(self):
        """Net losses (realized < 0) → on_track=False regardless of elapsed time."""
        goal = _make_goal(
            target=10_000_000,
            realized=-500_000,
            start_date="2026-01-01",
            deadline="2026-04-30",
        )
        with patch(ASSESS_REACHABILITY_PATH, return_value=(None, "")):
            result = compute_goal_metrics(
                goal,
                deployable=55_000_000,
                scan_date=date(2026, 1, 15),
                format_prose=False,
            )
        assert result["on_track"] is False

    def test_50_percent_progress_at_50_percent_time_is_on_track(self):
        """Exactly linear pace → on_track=True (50% >= 50% * 0.7 = 35%)."""
        goal = _make_goal(
            target=10_000_000,
            realized=5_000_000,
            start_date="2026-01-01",
            deadline="2026-03-31",
        )
        with patch(ASSESS_REACHABILITY_PATH, return_value=(None, "")):
            result = compute_goal_metrics(
                goal,
                deployable=20_000_000,
                scan_date=date(2026, 2, 15),
                format_prose=False,
            )
        assert result["on_track"] is True


# ---------------------------------------------------------------------------
# compute_goal_metrics — days_left with explicit scan_date
# ---------------------------------------------------------------------------


class TestComputeGoalMetricsDaysLeft:
    """days_left calculated relative to scan_date, not today."""

    def test_days_left_scan_date_april_1_deadline_april_10(self):
        goal = _make_goal(deadline="2026-04-10")
        with patch(ASSESS_REACHABILITY_PATH, return_value=(None, "")):
            result = compute_goal_metrics(
                goal,
                deployable=20_000_000,
                scan_date=date(2026, 4, 1),
                format_prose=False,
            )
        assert result["days_left"] == 9

    def test_days_left_scan_date_march_31_deadline_april_10(self):
        goal = _make_goal(deadline="2026-04-10")
        with patch(ASSESS_REACHABILITY_PATH, return_value=(None, "")):
            result = compute_goal_metrics(
                goal,
                deployable=20_000_000,
                scan_date=date(2026, 3, 31),
                format_prose=False,
            )
        assert result["days_left"] == 10


# ---------------------------------------------------------------------------
# is_long_horizon_goal
# ---------------------------------------------------------------------------


class TestIsLongHorizonGoal:
    @pytest.mark.parametrize(
        ("goal_type", "days_left", "expected"),
        [
            ("Monthly", 30, False),
            ("Monthly", 400, False),
            ("Quarterly", 400, False),
            ("Custom", 400, True),
            ("Annual", 366, True),
            ("Annual", 365, False),  # boundary: needs > 365
        ],
    )
    def test_parametrized(self, goal_type: str, days_left: int, expected: bool):
        assert is_long_horizon_goal(goal_type, days_left) is expected


# ---------------------------------------------------------------------------
# compute_directive_constraints
# ---------------------------------------------------------------------------


class TestComputeDirectiveConstraints:
    """Deterministic constraints from goals + cash."""

    def test_determined_urgency_goal_yields_correct_constraints(self):
        """DETERMINED urgency goal (from UNREACHABLE monthly) → min_rr=2.0, max_entries=5."""
        goal = {
            "name": "April Monthly",
            "goal_type": "Monthly",
            "target": 20_000_000,
            "realized": 1_000_000,
            "remaining": 39_000_000,
            "days_left": 9,
            "urgency": {
                "urgency": "DETERMINED",
                "min_rr": 2.0,
                "max_picks": 5,
                "note": "One disciplined trade can change momentum",
            },
        }
        cash = _make_cash(deployable=55_000_000)

        result = compute_directive_constraints([goal], cash)

        assert result["min_rr"] == 2.0
        assert result["max_new_entries"] == 5
        assert result["urgency_tier"] == "DETERMINED"


# ---------------------------------------------------------------------------
# compose_with_retro — anti-death-spiral: max() for entries, min() for R:R
# ---------------------------------------------------------------------------


class TestComposeWithRetro:
    """compose_with_retro takes more permissive value to prevent death spiral."""

    def test_retro_lower_max_entries_goal_wins(self):
        """retro max_entries=2 vs goal max_entries=3 → result=3 (max)."""
        constraints: PipelineConstraints = {
            "budget_vnd": 20_000_000,
            "max_new_entries": 3,
            "min_rr": 3.5,
            "urgency_tier": "DETERMINED",
            "goal_gap": 39_000_000,
            "deployable": 20_000_000,
        }
        retro = {"max_entries": 2, "min_rr_override": None, "constraint_text": "Retro tight"}

        result = compose_with_retro(constraints, retro)

        assert result["max_new_entries"] == 3  # max(3, 2) — goal wins

    def test_retro_higher_min_rr_goal_wins(self):
        """retro min_rr_override=3.0 vs goal min_rr=3.5 → result=3.0 (min)."""
        constraints: PipelineConstraints = {
            "budget_vnd": 20_000_000,
            "max_new_entries": 3,
            "min_rr": 3.5,
            "urgency_tier": "DETERMINED",
            "goal_gap": 39_000_000,
            "deployable": 20_000_000,
        }
        retro = {"max_entries": None, "min_rr_override": 3.0, "constraint_text": "Retro text"}

        result = compose_with_retro(constraints, retro)

        assert result["min_rr"] == 3.0  # min(3.5, 3.0) — retro wins (less restrictive R:R)

    def test_retro_constraint_text_stored(self):
        constraints: PipelineConstraints = {
            "budget_vnd": 20_000_000,
            "max_new_entries": 3,
            "min_rr": 3.5,
            "urgency_tier": "NORMAL",
            "goal_gap": 0,
            "deployable": 20_000_000,
        }
        retro = {
            "max_entries": None,
            "min_rr_override": None,
            "constraint_text": "Normal constraints apply",
        }

        result = compose_with_retro(constraints, retro)

        assert result["retro_constraint_text"] == "Normal constraints apply"


# ---------------------------------------------------------------------------
# apply_circuit_breakers
# ---------------------------------------------------------------------------


class TestApplyCircuitBreakers:
    """Hard floors/caps prevent death spiral."""

    def test_zero_max_entries_floored_to_1(self):
        constraints: PipelineConstraints = {
            "budget_vnd": 20_000_000,
            "max_new_entries": 0,
            "min_rr": 3.5,
            "urgency_tier": "NORMAL",
            "goal_gap": 0,
            "deployable": 20_000_000,
        }
        result = apply_circuit_breakers(constraints)
        assert result["max_new_entries"] == 1

    def test_min_rr_passed_through(self):
        """apply_circuit_breakers leaves min_rr to the composer.

        The R:R ceiling used to live here as CIRCUIT_BREAKER_RR_CAP=3.0, but
        was retired on 2026-04-20 when the composer
        (shared.rules.recommendation_gate) became the single source of truth
        for the effective R:R floor. This function is now a pure max_entries
        guard.
        """
        constraints: PipelineConstraints = {
            "budget_vnd": 20_000_000,
            "max_new_entries": 2,
            "min_rr": 5.0,
            "urgency_tier": "NORMAL",
            "goal_gap": 0,
            "deployable": 20_000_000,
        }
        result = apply_circuit_breakers(constraints)
        assert result["min_rr"] == 5.0
        assert result["max_new_entries"] == 2

    def test_valid_values_unchanged(self):
        """Already-valid constraints pass through unchanged."""
        constraints: PipelineConstraints = {
            "budget_vnd": 20_000_000,
            "max_new_entries": 3,
            "min_rr": 2.5,
            "urgency_tier": "DETERMINED",
            "goal_gap": 0,
            "deployable": 20_000_000,
        }
        result = apply_circuit_breakers(constraints)
        assert result["max_new_entries"] == 3
        assert result["min_rr"] == 2.5


# ---------------------------------------------------------------------------
# inject_entry_gate
# ---------------------------------------------------------------------------


class TestInjectEntryGate:
    def test_entries_allowed_false_reflected_in_dict(self):
        constraints: PipelineConstraints = {
            "budget_vnd": 20_000_000,
            "max_new_entries": 3,
            "min_rr": 3.5,
            "urgency_tier": "NORMAL",
            "goal_gap": 0,
            "deployable": 20_000_000,
        }
        result = inject_entry_gate(
            constraints,
            entries_allowed=False,
            entries_blocked_reason="Circuit breaker active",
        )
        assert result["entries_allowed"] is False
        assert result["entries_blocked_reason"] == "Circuit breaker active"

    def test_entries_allowed_true_no_reason_key(self):
        constraints: PipelineConstraints = {
            "budget_vnd": 20_000_000,
            "max_new_entries": 3,
            "min_rr": 3.5,
            "urgency_tier": "NORMAL",
            "goal_gap": 0,
            "deployable": 20_000_000,
        }
        result = inject_entry_gate(constraints, entries_allowed=True, entries_blocked_reason=None)
        assert result["entries_allowed"] is True
        assert "entries_blocked_reason" not in result


# ---------------------------------------------------------------------------
# PipelineConstraints TypedDict
# ---------------------------------------------------------------------------


class TestPipelineConstraintsTypedDict:
    """TypedDict contract — all expected keys exist as annotations."""

    EXPECTED_KEYS = {
        "budget_vnd",
        "max_new_entries",
        "min_rr",
        "urgency_tier",
        "goal_gap",
        "deployable",
        "retro_constraint_text",
        "retro_max_entries",
        "retro_scale_override",
        "retro_min_rr_override",
        "entries_allowed",
        "entries_blocked_reason",
    }

    def test_all_expected_keys_in_annotations(self):
        annotations = PipelineConstraints.__annotations__
        missing = self.EXPECTED_KEYS - set(annotations.keys())
        assert not missing, f"Missing keys in PipelineConstraints: {missing}"
