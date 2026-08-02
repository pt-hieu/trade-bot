"""Tests for shared/rules/expectancy.py — Van Tharp R-multiple floor."""

import pytest

from shared.rules.expectancy import compute_expectancy_floor
from shared.rules.rr_floors import get_rr_floor


class TestComputeExpectancyFloor:
    """compute_expectancy_floor solves for min R:R s.t. E ≥ 0.3R."""

    def test_none_win_rate_fail_closed(self):
        """Missing data → conservative high floor."""
        assert compute_expectancy_floor(None) == 4.0

    def test_zero_win_rate_fail_closed(self):
        """Zero wins → conservative high floor."""
        assert compute_expectancy_floor(0) == 4.0

    def test_perfect_win_rate_minimum_floor(self):
        """100% win rate still demands floor of 2.0 (asymmetry)."""
        assert compute_expectancy_floor(1.0) == 2.0

    def test_low_win_rate_demands_high_rr(self):
        """25% win rate → (1.3 - 0.25) / 0.25 = 4.2."""
        assert compute_expectancy_floor(0.25) == pytest.approx(4.2, rel=1e-3)

    def test_moderate_win_rate(self):
        """40% win rate → (1.3 - 0.4) / 0.4 = 2.25."""
        assert compute_expectancy_floor(0.40) == pytest.approx(2.25, rel=1e-3)

    def test_high_win_rate_clamped_to_floor_floor(self):
        """50%+ win rate keeps floor at 2.0 (formula goes below)."""
        assert compute_expectancy_floor(0.55) == 2.0
        assert compute_expectancy_floor(0.65) == 2.0

    def test_break_even_at_floor(self):
        """At the computed floor, expectancy ≈ 0.3R per trade."""
        win_rate = 0.30
        floor = compute_expectancy_floor(win_rate)
        expectancy = win_rate * floor - (1 - win_rate)
        assert expectancy == pytest.approx(0.3, rel=1e-3)


class TestGetRrFloorWithExpectancy:
    """get_rr_floor takes max of goal/regime/expectancy floors."""

    def test_expectancy_floor_dominates_when_high(self):
        """Cold streak (low win rate) raises the floor above goal urgency."""
        # min_rr from goal = 3.0; expectancy floor at win_rate=0.25 = 4.2
        assert get_rr_floor("CALM", min_rr=3.0, expectancy_floor=4.2) == 4.2

    def test_regime_floor_dominates_when_higher(self):
        """ELEVATED regime floor (3.0) wins over expectancy 2.5."""
        assert get_rr_floor("ELEVATED", min_rr=2.0, expectancy_floor=2.5) == 3.0

    def test_no_expectancy_floor_falls_back_to_baseline(self):
        """None expectancy_floor preserves prior behavior."""
        assert get_rr_floor("CALM", min_rr=3.0) == 3.0

    def test_crisis_regime_caps_below_expectancy_when_lower(self):
        """CRISIS=4.5 still wins when expectancy floor is lower."""
        assert get_rr_floor("CRISIS", min_rr=3.0, expectancy_floor=3.5) == 4.5

    def test_expectancy_above_crisis_dominates(self):
        """A 5.0 expectancy floor beats CRISIS 4.5."""
        assert get_rr_floor("CRISIS", min_rr=3.0, expectancy_floor=5.0) == 5.0
