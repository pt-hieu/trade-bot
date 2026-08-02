"""Tests for centralized geopolitical shock phase config and date parsing."""

from datetime import date

import pytest

from shared.rules.geopolitical import (
    ACTIVE_SHOCK_PHASES,
    GEOPOLITICAL_PHASES,
    PHASE_SEVERITY,
    REGIME_FLOOR_MAP,
    SHOCK_MULTIPLIER_MAP,
    parse_phase_period,
    validate_phase_periods,
)


class TestPhaseConfig:
    """Verify derived maps are computed correctly from GEOPOLITICAL_PHASES."""

    def test_all_phases_have_severity(self):
        assert set(PHASE_SEVERITY.keys()) == set(GEOPOLITICAL_PHASES.keys())

    def test_all_phases_have_multiplier(self):
        assert set(SHOCK_MULTIPLIER_MAP.keys()) == set(GEOPOLITICAL_PHASES.keys())

    def test_active_phases_match_config(self):
        expected = {
            name for name, config in GEOPOLITICAL_PHASES.items() if config.active_for_agents
        }
        assert expected == ACTIVE_SHOCK_PHASES

    def test_regime_floor_excludes_none(self):
        for name, floor in REGIME_FLOOR_MAP.items():
            assert floor is not None
            config = GEOPOLITICAL_PHASES[name]
            assert config.regime_floor == floor

    def test_immediate_shock_is_highest_severity(self):
        assert PHASE_SEVERITY["immediate_shock"] == max(PHASE_SEVERITY.values())

    def test_resolution_has_lowest_severity(self):
        assert PHASE_SEVERITY["resolution_or_escalation"] == min(PHASE_SEVERITY.values())

    def test_resolution_has_no_regime_floor(self):
        assert "resolution_or_escalation" not in REGIME_FLOOR_MAP

    def test_resolution_has_gentle_multiplier(self):
        assert SHOCK_MULTIPLIER_MAP["resolution_or_escalation"] == 0.9


class TestParsePhasePeriod:
    """Test all supported date formats for parse_phase_period()."""

    @pytest.mark.parametrize(
        "period,expected_start,expected_end,expected_open",
        [
            # Standard open-ended with day
            ("Mar 1, 2026+", date(2026, 3, 1), None, True),
            ("Apr 15, 2026+", date(2026, 4, 15), None, True),
            # Month-only open-ended (the format that caused the original bug)
            ("Apr 2026+", date(2026, 4, 1), None, True),
            ("Jan 2027+", date(2027, 1, 1), None, True),
            # Same-month bounded range
            ("Mar 1-7, 2026", date(2026, 3, 1), date(2026, 3, 7), False),
            ("Mar 8-31, 2026", date(2026, 3, 8), date(2026, 3, 31), False),
            # Misplaced plus after day: "Sep 21+, 2026" → treated as "Sep 21, 2026+"
            ("Sep 21+, 2026", date(2026, 9, 21), None, True),
            ("Mar 1+, 2026", date(2026, 3, 1), None, True),
            # Cross-month bounded range
            (
                "Mar 28 - Apr 5, 2026",
                date(2026, 3, 28),
                date(2026, 4, 5),
                False,
            ),
            (
                "Dec 28 - Jan 5, 2027",
                date(2027, 12, 28),
                date(2027, 1, 5),
                False,
            ),
        ],
    )
    def test_valid_periods(
        self, period: str, expected_start: date, expected_end: date | None, expected_open: bool
    ):
        start, end, is_open = parse_phase_period(period)
        assert start == expected_start
        assert end == expected_end
        assert is_open == expected_open

    @pytest.mark.parametrize(
        "period",
        [
            "",
            "invalid",
            "2026",
            "Mar 2026",  # no + suffix
            "13th Month 2026+",
        ],
    )
    def test_invalid_periods_return_none(self, period: str):
        start, end, is_open = parse_phase_period(period)
        assert start is None
        assert end is None
        assert is_open is False


class TestValidatePhasesPeriods:
    """Test write-time validation of phase periods."""

    def test_valid_phases_no_errors(self):
        phases = {
            "immediate_shock": {"period": "Mar 1-7, 2026", "impact": "NEGATIVE"},
            "sustained_pressure": {"period": "Mar 8, 2026+", "impact": "NEGATIVE"},
        }
        errors = validate_phase_periods(phases)
        assert errors == []

    def test_invalid_period_returns_error(self):
        phases = {
            "bad_phase": {"period": "not a date", "impact": "NEGATIVE"},
        }
        errors = validate_phase_periods(phases)
        assert len(errors) == 1
        assert "unparseable" in errors[0].lower()

    def test_missing_period_returns_error(self):
        phases = {
            "empty_phase": {"impact": "NEGATIVE"},
        }
        errors = validate_phase_periods(phases)
        assert len(errors) == 1
        assert "missing" in errors[0].lower()

    def test_non_dict_phase_info_returns_error(self):
        phases = {"bad_phase": "not a dict"}
        errors = validate_phase_periods(phases)
        assert len(errors) == 1
        assert "not a dict" in errors[0].lower()

    def test_production_hormuz_data_valid(self):
        """Regression: actual Hormuz crisis data from migration 151 must validate."""
        phases = {
            "immediate_shock": {
                "impact": "NEGATIVE",
                "period": "Mar 1-7, 2026",
                "behavior": "Panic selling",
            },
            "sustained_pressure": {
                "impact": "NEGATIVE",
                "period": "Mar 8-31, 2026",
                "behavior": "Sustained high oil prices",
            },
            "resolution_or_escalation": {
                "impact": "NEUTRAL",
                "period": "Apr 1, 2026+",
                "behavior": "Diplomatic resolution or deeper selloff",
            },
        }
        errors = validate_phase_periods(phases)
        assert errors == []

    def test_original_bug_format_also_valid(self):
        """The 'Apr 2026+' format that caused the bug should now be parseable."""
        phases = {
            "resolution_or_escalation": {
                "period": "Apr 2026+",
                "impact": "NEUTRAL",
            },
        }
        errors = validate_phase_periods(phases)
        assert errors == []
