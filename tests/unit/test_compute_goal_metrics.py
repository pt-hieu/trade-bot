"""Tests for _compute_goal_metrics() in portfolio_goals.py."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from shared.rules.constraints import compute_goal_metrics as _compute_goal_metrics


def _make_goal(
    *,
    name: str = "Monthly Cash Goal",
    goal_type: str = "Monthly",
    target: float = 10_000_000,
    realized: float = 5_000_000,
    deadline: str | date | None = None,
    trades_count: int = 3,
) -> dict:
    """Build a minimal goal dict for testing."""
    deadline_value = deadline or (datetime.now() + timedelta(days=25)).strftime("%Y-%m-%d")
    return {
        "name": name,
        "goal_type": goal_type,
        "target": target,
        "realized": realized,
        "deadline": deadline_value,
        "trades_count": trades_count,
    }


REACHABILITY_PATH = "shared.rules.constraints.assess_reachability"


class TestBasicMetrics:
    """Core derived fields: name, progress, days_left, daily_target."""

    def test_name_passthrough(self):
        goal = _make_goal(name="Q1 Profit Target")
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["name"] == "Q1 Profit Target"

    def test_goal_type_passthrough(self):
        goal = _make_goal(goal_type="Quarterly")
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["goal_type"] == "Quarterly"

    def test_target_and_realized_passthrough(self):
        goal = _make_goal(target=20_000_000, realized=8_000_000)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["target"] == 20_000_000
        assert result["realized"] == 8_000_000

    def test_remaining_computed(self):
        goal = _make_goal(target=10_000_000, realized=3_000_000)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["remaining"] == 7_000_000

    def test_progress_pct_computed(self):
        goal = _make_goal(target=10_000_000, realized=2_500_000)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["progress_pct"] == 25.0

    def test_progress_pct_zero_target_does_not_raise(self):
        goal = _make_goal(target=0, realized=0)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["progress_pct"] == 0

    def test_days_left_from_future_deadline(self):
        future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        goal = _make_goal(deadline=future)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        # Allow ±1 day rounding from datetime.now() precision
        assert 28 <= result["days_left"] <= 31

    def test_days_left_never_negative(self):
        past = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        goal = _make_goal(deadline=past)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["days_left"] == 0

    def test_daily_target_computed(self):
        future = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        goal = _make_goal(target=10_000_000, realized=0, deadline=future)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        # remaining=10M over ~10 days ≈ 1_000_000/day
        assert result["daily_target"] > 0

    def test_daily_target_zero_when_no_days_left(self):
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        goal = _make_goal(deadline=past)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["daily_target"] == 0

    def test_trades_count_passthrough(self):
        goal = _make_goal(trades_count=7)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["trades_count"] == 7

    def test_urgency_key_present(self):
        goal = _make_goal()
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert "urgency" in result

    def test_prose_key_present(self):
        goal = _make_goal()
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert "prose" in result


class TestOnTrackDetermination:
    """on_track logic: pace-based when start_date provided, fallback days_left > 20."""

    def test_pace_based_on_track_when_ahead_of_schedule(self):
        """With start_date, realized >= 70% of expected linear pace → on_track."""
        start = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        deadline = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        # 20 days elapsed of 30 total → expected progress = 20/30 * 10M = 6.67M * 0.7 = 4.67M
        goal = _make_goal(target=10_000_000, realized=5_000_000, deadline=deadline)
        goal["start_date"] = start
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["on_track"] is True

    def test_pace_based_off_track_when_far_behind(self):
        """With start_date, realized < 70% of expected pace → off_track."""
        start = (datetime.now() - timedelta(days=25)).strftime("%Y-%m-%d")
        deadline = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        # 25 of 30 days elapsed → expected = 25/30 * 10M = 8.33M * 0.7 = 5.83M; realized 1M < threshold
        goal = _make_goal(target=10_000_000, realized=1_000_000, deadline=deadline)
        goal["start_date"] = start
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["on_track"] is False

    def test_days_left_over_20_is_on_track(self):
        goal = _make_goal(
            realized=0, deadline=(datetime.now() + timedelta(days=25)).strftime("%Y-%m-%d")
        )
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["on_track"] is True

    def test_normal_urgency_when_on_track_reachable(self):
        """on_track + reachable (achievability=None) → NORMAL urgency."""
        goal = _make_goal(
            realized=5_000_000, deadline=(datetime.now() + timedelta(days=25)).strftime("%Y-%m-%d")
        )
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["urgency"]["urgency"] == "NORMAL"


class TestAchievabilityOnTrack:
    """achievability=ON_TRACK set when reachable and on_track."""

    def test_on_track_reachable_sets_on_track_achievability(self):
        goal = _make_goal(
            realized=5_000_000, deadline=(datetime.now() + timedelta(days=25)).strftime("%Y-%m-%d")
        )
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result.get("achievability") == "ON_TRACK"

    def test_stretch_achievability_preserved(self):
        goal = _make_goal(deadline=(datetime.now() + timedelta(days=25)).strftime("%Y-%m-%d"))
        with patch(REACHABILITY_PATH, return_value=("STRETCH", "Achievable but tight")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["achievability"] == "STRETCH"
        assert result["achievability_note"] == "Achievable but tight"


class TestDeterminedOverride:
    """UNREACHABLE + short-horizon goal → DETERMINED urgency, on_track=False."""

    def test_unreachable_monthly_triggers_determined(self):
        goal = _make_goal(
            goal_type="Monthly",
            deadline=(datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d"),
        )
        with patch(REACHABILITY_PATH, return_value=("UNREACHABLE", "Too far behind")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["urgency"]["urgency"] == "DETERMINED"
        assert result["urgency"]["min_rr"] == 2.0
        assert result["urgency"]["max_picks"] == 5
        assert result["on_track"] is False

    def test_unreachable_quarterly_triggers_determined(self):
        goal = _make_goal(
            goal_type="Quarterly",
            deadline=(datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d"),
        )
        with patch(REACHABILITY_PATH, return_value=("UNREACHABLE", "Too far behind")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["urgency"]["urgency"] == "DETERMINED"

    def test_determined_note_present(self):
        goal = _make_goal(
            goal_type="Monthly",
            deadline=(datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d"),
        )
        with patch(REACHABILITY_PATH, return_value=("UNREACHABLE", "Needs cash injection")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert "note" in result["urgency"]

    def test_determined_prevents_aggressive_death_spiral(self):
        """The old AGGRESSIVE tier had min_rr=6.0 which created 0 entries.
        DETERMINED uses min_rr=3.5 to keep the pipeline active."""
        goal = _make_goal(
            goal_type="Monthly",
            deadline=(datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
        )
        with patch(REACHABILITY_PATH, return_value=("UNREACHABLE", "Goal unreachable")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["urgency"]["min_rr"] < 6.0
        assert result["urgency"]["urgency"] != "AGGRESSIVE"

    def test_unreachable_sets_achievability_on_result(self):
        goal = _make_goal(
            goal_type="Monthly",
            deadline=(datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d"),
        )
        with patch(REACHABILITY_PATH, return_value=("UNREACHABLE", "Too far behind")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["achievability"] == "UNREACHABLE"
        assert result["achievability_note"] == "Too far behind"


class TestLongHorizonExclusion:
    """UNREACHABLE + long-horizon goal (non Monthly/Quarterly AND days_left > 365)
    does NOT trigger DETERMINED override."""

    def test_annual_goal_over_365_days_no_determined(self):
        goal = _make_goal(
            goal_type="Annual",
            deadline=(datetime.now() + timedelta(days=400)).strftime("%Y-%m-%d"),
        )
        with patch(REACHABILITY_PATH, return_value=("UNREACHABLE", "Long way to go")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["urgency"]["urgency"] != "DETERMINED"

    def test_custom_goal_type_over_365_days_no_determined(self):
        goal = _make_goal(
            goal_type="LongTerm",
            deadline=(datetime.now() + timedelta(days=500)).strftime("%Y-%m-%d"),
        )
        with patch(REACHABILITY_PATH, return_value=("UNREACHABLE", "Long way to go")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["urgency"]["urgency"] != "DETERMINED"

    def test_monthly_over_365_days_still_triggers_determined(self):
        """Monthly goal type is always short-horizon, even with far deadline."""
        goal = _make_goal(
            goal_type="Monthly",
            deadline=(datetime.now() + timedelta(days=400)).strftime("%Y-%m-%d"),
        )
        with patch(REACHABILITY_PATH, return_value=("UNREACHABLE", "Unreachable")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["urgency"]["urgency"] == "DETERMINED"

    def test_quarterly_over_365_days_still_triggers_determined(self):
        """Quarterly goal type is always short-horizon, even with far deadline."""
        goal = _make_goal(
            goal_type="Quarterly",
            deadline=(datetime.now() + timedelta(days=400)).strftime("%Y-%m-%d"),
        )
        with patch(REACHABILITY_PATH, return_value=("UNREACHABLE", "Unreachable")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["urgency"]["urgency"] == "DETERMINED"

    def test_annual_under_365_days_triggers_determined(self):
        """Annual goal type with ≤365 days_left → not long-horizon → DETERMINED."""
        goal = _make_goal(
            goal_type="Annual",
            deadline=(datetime.now() + timedelta(days=200)).strftime("%Y-%m-%d"),
        )
        with patch(REACHABILITY_PATH, return_value=("UNREACHABLE", "Unreachable")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["urgency"]["urgency"] == "DETERMINED"


class TestDeadlineParsing:
    """Deadline field accepts string, date object, or None."""

    def test_string_deadline_parsed(self):
        future_str = (datetime.now() + timedelta(days=20)).strftime("%Y-%m-%d")
        goal = _make_goal(deadline=future_str)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["days_left"] > 0

    def test_date_object_deadline_parsed(self):
        future_date = (datetime.now() + timedelta(days=20)).date()
        goal = _make_goal(deadline=future_date)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["days_left"] > 0

    def test_missing_deadline_gives_zero_days(self):
        goal = {
            "name": "No Deadline Goal",
            "goal_type": "Monthly",
            "target": 10_000_000,
            "realized": 5_000_000,
            "deadline": "",
            "trades_count": 2,
        }
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["days_left"] == 0

    def test_none_deadline_gives_zero_days(self):
        goal = {
            "name": "None Deadline Goal",
            "goal_type": "Monthly",
            "target": 10_000_000,
            "realized": 5_000_000,
            "deadline": None,
            "trades_count": 2,
        }
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["days_left"] == 0

    def test_deadline_string_preserved_in_result(self):
        future_str = (datetime.now() + timedelta(days=20)).strftime("%Y-%m-%d")
        goal = _make_goal(deadline=future_str)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert result["deadline"] == future_str

    def test_date_object_converted_to_string_in_result(self):
        future_date = (datetime.now() + timedelta(days=20)).date()
        goal = _make_goal(deadline=future_date)
        with patch(REACHABILITY_PATH, return_value=(None, "")):
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        assert isinstance(result["deadline"], str)


class TestReachabilityNotCalledWhenNotNeeded:
    """_assess_reachability is only called when remaining > 0 AND days_left > 0."""

    def test_reachability_skipped_when_zero_remaining(self):
        goal = _make_goal(target=5_000_000, realized=5_000_000)
        with patch(
            REACHABILITY_PATH, return_value=("UNREACHABLE", "Should not appear")
        ) as mock_assess:
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        mock_assess.assert_not_called()
        assert "achievability" not in result

    def test_reachability_skipped_when_zero_days_left(self):
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        goal = _make_goal(deadline=past)
        with patch(
            REACHABILITY_PATH, return_value=("UNREACHABLE", "Should not appear")
        ) as mock_assess:
            result = _compute_goal_metrics(goal, deployable=50_000_000)
        mock_assess.assert_not_called()
        assert "achievability" not in result
