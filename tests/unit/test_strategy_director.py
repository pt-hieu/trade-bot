"""Unit tests for strategy director deterministic constraints."""

from shared.rules.constraints import (
    compute_directive_constraints,
)
from shared.rules.constraints import (
    select_most_urgent_goal as _most_urgent_goal,
)


def _make_goal(urgency_tier="NORMAL", min_rr=3.0, max_picks=5, name="Test Goal"):
    """Helper to build goal dict with urgency."""
    return {
        "name": name,
        "target": 10_000_000,
        "realized": 3_000_000,
        "remaining": 7_000_000,
        "progress_pct": 30.0,
        "days_left": 20,
        "urgency": {
            "urgency": urgency_tier,
            "min_rr": min_rr,
            "max_picks": max_picks,
        },
    }


def _make_cash(deployable=20_000_000):
    """Helper to build cash dict."""
    return {
        "total_cash": deployable + 10_000_000,
        "min_reserve": 10_000_000,
        "deployable": deployable,
        "can_trade": deployable > 5_000_000,
    }


class TestComputeDirectiveConstraints:
    """Tests for compute_directive_constraints()."""

    def test_normal_healthy_cash(self):
        """Healthy cash, on track — normal constraints."""
        goals = [_make_goal("NORMAL", 3.0, 5)]
        cash = _make_cash(20_000_000)

        result = compute_directive_constraints(goals, cash)

        assert result["budget_vnd"] == 20_000_000
        assert result["max_new_entries"] == 5
        assert result["min_rr"] == 3.0
        assert result["urgency_tier"] == "NORMAL"

    def test_no_cash_zero_entries(self):
        """Zero deployable cash — max_entries must be 0."""
        goals = [_make_goal("NORMAL", 3.0, 5)]
        cash = _make_cash(0)

        result = compute_directive_constraints(goals, cash)

        assert result["budget_vnd"] == 0
        assert result["max_new_entries"] == 0

    def test_high_urgency_constraints(self):
        """HIGH urgency — min_rr=5.0, max_picks=2."""
        goals = [_make_goal("HIGH", 5.0, 2)]
        cash = _make_cash(15_000_000)

        result = compute_directive_constraints(goals, cash)

        assert result["min_rr"] == 5.0
        assert result["max_new_entries"] == 2
        assert result["urgency_tier"] == "HIGH"

    def test_acceptance_no_entries(self):
        """ACCEPTANCE urgency — 1 entry allowed (circuit breaker prevents total lock-out)."""
        goals = [_make_goal("ACCEPTANCE", None, 0)]
        cash = _make_cash(20_000_000)

        result = compute_directive_constraints(goals, cash)

        assert result["max_new_entries"] == 1
        assert result["urgency_tier"] == "ACCEPTANCE"

    def test_elevated_constraints(self):
        """ELEVATED urgency — min_rr=4.0, max_picks=3."""
        goals = [_make_goal("ELEVATED", 4.0, 3)]
        cash = _make_cash(10_000_000)

        result = compute_directive_constraints(goals, cash)

        assert result["max_new_entries"] == 3
        assert result["min_rr"] == 4.0

    def test_no_goals_defaults(self):
        """No active goals — defaults to NORMAL urgency.

        Values track MIN_RR_NORMAL (2.5) + MAX_PICKS_NORMAL (3) in
        shared/rules/constraints.py. Both lowered by the 2026-02-28
        anti-conservatism-death-spiral work.
        """
        goals = []
        cash = _make_cash(20_000_000)

        result = compute_directive_constraints(goals, cash)

        assert result["urgency_tier"] == "NORMAL"
        assert result["min_rr"] == 2.5
        assert result["max_new_entries"] == 3

    def test_multi_goal_most_urgent_wins(self):
        """Two goals with different urgencies — most urgent wins."""
        goals = [
            _make_goal("NORMAL", 3.0, 5, name="Monthly Cash"),
            _make_goal("HIGH", 5.0, 2, name="Emergency Fund"),
        ]
        cash = _make_cash(15_000_000)

        result = compute_directive_constraints(goals, cash)

        assert result["urgency_tier"] == "HIGH"
        assert result["min_rr"] == 5.0
        assert result["max_new_entries"] == 2

    def test_multi_goal_acceptance_overrides_normal(self):
        """ACCEPTANCE goal overrides NORMAL — 1 entry (circuit breaker)."""
        goals = [
            _make_goal("NORMAL", 3.0, 5, name="Monthly Cash"),
            _make_goal("ACCEPTANCE", None, 0, name="Expired Goal"),
        ]
        cash = _make_cash(20_000_000)

        result = compute_directive_constraints(goals, cash)

        assert result["urgency_tier"] == "ACCEPTANCE"
        assert result["max_new_entries"] == 1


class TestMostUrgentGoal:
    """Tests for _most_urgent_goal()."""

    def test_empty_list(self):
        assert _most_urgent_goal([]) is None

    def test_single_goal(self):
        goal = _make_goal("HIGH", 5.0, 2)
        assert _most_urgent_goal([goal]) == goal

    def test_picks_highest_urgency(self):
        goals = [
            _make_goal("NORMAL", 3.0, 5, name="A"),
            _make_goal("ELEVATED", 4.0, 3, name="B"),
            _make_goal("AWARENESS", 3.0, 5, name="C"),
        ]
        result = _most_urgent_goal(goals)
        assert result["name"] == "B"
