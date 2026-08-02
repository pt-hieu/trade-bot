"""Tests for is_long_horizon_goal() — prevents 4-year goals from blocking daily entries."""

import pytest

from shared.rules.constraints import is_long_horizon_goal


class TestShortHorizonGoals:
    """Monthly and Quarterly goals are always short-horizon."""

    def test_monthly_is_short_horizon(self):
        assert is_long_horizon_goal("Monthly", days_left=30) is False

    def test_monthly_even_with_many_days(self):
        """Monthly with 400 days left is still short-horizon (goal_type wins)."""
        assert is_long_horizon_goal("Monthly", days_left=400) is False

    def test_quarterly_is_short_horizon(self):
        assert is_long_horizon_goal("Quarterly", days_left=90) is False

    def test_quarterly_even_with_many_days(self):
        assert is_long_horizon_goal("Quarterly", days_left=500) is False


class TestLongHorizonGoals:
    """Non-Monthly/Quarterly goals with >365 days are long-horizon."""

    def test_annual_over_365_is_long_horizon(self):
        assert is_long_horizon_goal("Annual", days_left=366) is True

    def test_custom_type_over_365_is_long_horizon(self):
        assert is_long_horizon_goal("4-Year Wealth", days_left=1200) is True

    def test_annual_exactly_365_is_not_long_horizon(self):
        """Boundary: exactly 365 days is NOT long-horizon (needs >365)."""
        assert is_long_horizon_goal("Annual", days_left=365) is False

    def test_annual_under_365_is_not_long_horizon(self):
        assert is_long_horizon_goal("Annual", days_left=100) is False


class TestBoundaryConditions:
    """Edge cases and boundary values."""

    def test_zero_days_left(self):
        assert is_long_horizon_goal("Annual", days_left=0) is False

    def test_negative_days_left(self):
        assert is_long_horizon_goal("Annual", days_left=-5) is False

    @pytest.mark.parametrize(
        ("goal_type", "days_left", "expected"),
        [
            ("Monthly", 0, False),
            ("Monthly", 365, False),
            ("Monthly", 366, False),
            ("Quarterly", 364, False),
            ("Quarterly", 366, False),
            ("Annual", 364, False),
            ("Annual", 365, False),
            ("Annual", 366, True),
            ("Custom", 366, True),
            ("Custom", 365, False),
        ],
    )
    def test_parametrized_matrix(self, goal_type: str, days_left: int, expected: bool):
        assert is_long_horizon_goal(goal_type, days_left) is expected
