"""Regression tests using actual production data from Hormuz crisis migration 151.

These tests verify that the phase resolution works with real JSONB data
from the catalysts table, not just synthetically generated dates.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from shared.neon.catalyst_summaries import _get_current_phase

# Exact JSONB from migration 151 (with corrected period for resolution phase)
HORMUZ_PHASES_CORRECTED = {
    "immediate_shock": {
        "impact": "NEGATIVE",
        "period": "Mar 1-7, 2026",
        "behavior": "Panic selling, oil gap up, airline/steel hammered. Energy names may spike on sentiment.",
    },
    "sustained_pressure": {
        "impact": "NEGATIVE",
        "period": "Mar 8-31, 2026",
        "behavior": "Sustained high oil prices pressure margins across transport, steel, plastics. CPI fears. VND under pressure.",
    },
    "resolution_or_escalation": {
        "impact": "NEUTRAL",
        "period": "Apr 1, 2026+",
        "behavior": "Diplomatic resolution leads to sharp recovery rally. Escalation leads to deeper selloff, defensive rotation to utilities/banks.",
    },
}

# Original buggy JSONB (month-only format)
HORMUZ_PHASES_ORIGINAL_BUG = {
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
        "period": "Apr 2026+",
        "behavior": "Diplomatic resolution or escalation",
    },
}


def _mock_today(target_date: date):
    """Pin `date.today()` inside catalyst_lifecycle to target_date.

    catalyst_summaries._get_current_phase delegates to resolve_phase_status
    which calls `date.today()` from shared.rules.catalyst_lifecycle. We patch
    that module's `date` binding with a MagicMock whose `.today()` returns
    the target while all other attributes fall through to the real `date`.
    """
    mock_date = MagicMock(wraps=date)
    mock_date.today.return_value = target_date
    return patch("shared.rules.catalyst_lifecycle.date", mock_date)


class TestHormuzImmediateShockPhase:
    """Phase resolution during immediate_shock period (Mar 1-7, 2026)."""

    def test_mar_1_resolves_to_immediate_shock(self):
        with _mock_today(date(2026, 3, 1)):
            phase_name, phase_info, days_active = _get_current_phase(HORMUZ_PHASES_CORRECTED)
            assert phase_name == "immediate_shock"
            assert phase_info is not None
            assert days_active == 0

    def test_mar_7_still_immediate_shock(self):
        with _mock_today(date(2026, 3, 7)):
            phase_name, _, _ = _get_current_phase(HORMUZ_PHASES_CORRECTED)
            assert phase_name == "immediate_shock"


class TestHormuzSustainedPressurePhase:
    """Phase resolution during sustained_pressure period (Mar 8-31, 2026)."""

    def test_mar_8_resolves_to_sustained_pressure(self):
        with _mock_today(date(2026, 3, 8)):
            phase_name, _, _ = _get_current_phase(HORMUZ_PHASES_CORRECTED)
            assert phase_name == "sustained_pressure"

    def test_mar_31_still_sustained_pressure(self):
        with _mock_today(date(2026, 3, 31)):
            phase_name, _, _ = _get_current_phase(HORMUZ_PHASES_CORRECTED)
            assert phase_name == "sustained_pressure"


class TestHormuzResolutionPhase:
    """Phase resolution during resolution_or_escalation period (Apr 1, 2026+)."""

    def test_apr_1_resolves_to_resolution(self):
        with _mock_today(date(2026, 4, 1)):
            phase_name, phase_info, days_active = _get_current_phase(HORMUZ_PHASES_CORRECTED)
            assert phase_name == "resolution_or_escalation"
            assert phase_info is not None
            assert days_active == 0

    def test_apr_15_still_resolution(self):
        with _mock_today(date(2026, 4, 15)):
            phase_name, _, days_active = _get_current_phase(HORMUZ_PHASES_CORRECTED)
            assert phase_name == "resolution_or_escalation"
            assert days_active == 14

    def test_resolution_expires_after_90_days(self):
        expired_date = date(2026, 4, 1) + timedelta(days=91)
        with _mock_today(expired_date):
            phase_name, phase_info, _ = _get_current_phase(HORMUZ_PHASES_CORRECTED)
            assert phase_name is None
            assert phase_info is None


class TestOriginalBugFormat:
    """Regression: 'Apr 2026+' (no day) must now resolve instead of silently failing."""

    def test_apr_2026_plus_resolves_on_apr_1(self):
        with _mock_today(date(2026, 4, 1)):
            phase_name, _, _ = _get_current_phase(HORMUZ_PHASES_ORIGINAL_BUG)
            assert phase_name == "resolution_or_escalation"

    def test_apr_2026_plus_resolves_on_apr_15(self):
        with _mock_today(date(2026, 4, 15)):
            phase_name, _, days_active = _get_current_phase(HORMUZ_PHASES_ORIGINAL_BUG)
            assert phase_name == "resolution_or_escalation"
            assert days_active == 14


class TestGapBetweenPhases:
    """No gap day between sustained_pressure end and resolution_or_escalation start."""

    def test_no_gap_on_apr_1(self):
        """Apr 1 should match resolution_or_escalation, not be a dead zone."""
        with _mock_today(date(2026, 4, 1)):
            phase_name, _, _ = _get_current_phase(HORMUZ_PHASES_CORRECTED)
            assert phase_name is not None
            assert phase_name == "resolution_or_escalation"
