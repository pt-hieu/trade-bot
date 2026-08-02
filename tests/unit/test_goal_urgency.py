"""Tests for deterministic goal urgency tier calculation."""

from shared.rules.constraints import calculate_goal_urgency


class TestGoalUrgency:
    """Urgency tier from (on_track, days_left) → tier + constraints."""

    def test_on_track_returns_normal(self):
        result = calculate_goal_urgency(on_track=True, days_left=25)
        assert result["urgency"] == "NORMAL"
        assert result["min_rr"] == 2.5
        assert result["max_picks"] == 3

    def test_on_track_ignores_days_left(self):
        """Even 1 day left is NORMAL if on_track."""
        result = calculate_goal_urgency(on_track=True, days_left=1)
        assert result["urgency"] == "NORMAL"

    def test_behind_many_days_awareness(self):
        result = calculate_goal_urgency(on_track=False, days_left=20)
        assert result["urgency"] == "AWARENESS"
        assert result["min_rr"] == 2.5
        assert result["max_picks"] == 4
        assert "note" in result

    def test_behind_boundary_16_days(self):
        result = calculate_goal_urgency(on_track=False, days_left=16)
        assert result["urgency"] == "AWARENESS"

    def test_behind_boundary_15_days(self):
        """Exactly 15 days → still AWARENESS (> 15 false, so ELEVATED)."""
        result = calculate_goal_urgency(on_track=False, days_left=15)
        assert result["urgency"] == "ELEVATED"

    def test_elevated_tier(self):
        result = calculate_goal_urgency(on_track=False, days_left=12)
        assert result["urgency"] == "ELEVATED"
        assert result["min_rr"] == 2.3
        assert result["max_picks"] == 4

    def test_behind_boundary_10_days(self):
        result = calculate_goal_urgency(on_track=False, days_left=10)
        assert result["urgency"] == "HIGH"

    def test_high_tier(self):
        result = calculate_goal_urgency(on_track=False, days_left=7)
        assert result["urgency"] == "HIGH"
        assert result["min_rr"] == 2.0
        assert result["max_picks"] == 5

    def test_behind_boundary_5_days(self):
        result = calculate_goal_urgency(on_track=False, days_left=5)
        assert result["urgency"] == "ACCEPTANCE"

    def test_acceptance_tier(self):
        result = calculate_goal_urgency(on_track=False, days_left=3)
        assert result["urgency"] == "ACCEPTANCE"
        assert result["min_rr"] == 2.0
        assert result["max_picks"] == 3
        assert "note" in result

    def test_zero_days_acceptance(self):
        result = calculate_goal_urgency(on_track=False, days_left=0)
        assert result["urgency"] == "ACCEPTANCE"

    def test_urgency_rr_monotonically_decreases(self):
        """Higher urgency → lower min_rr (flipped relationship)."""
        normal = calculate_goal_urgency(on_track=True, days_left=25)
        awareness = calculate_goal_urgency(on_track=False, days_left=20)
        elevated = calculate_goal_urgency(on_track=False, days_left=12)
        high = calculate_goal_urgency(on_track=False, days_left=7)
        acceptance = calculate_goal_urgency(on_track=False, days_left=3)

        assert normal["min_rr"] >= awareness["min_rr"]
        assert awareness["min_rr"] >= elevated["min_rr"]
        assert elevated["min_rr"] >= high["min_rr"]
        assert high["min_rr"] >= acceptance["min_rr"]
