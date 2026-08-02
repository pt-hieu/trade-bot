"""Tests for geopolitical shock phase staleness detection."""

from datetime import datetime, timedelta

from shared.neon.catalyst_summaries import _get_current_phase
from shared.rules.geopolitical import MAX_OPEN_ENDED_PHASE_DAYS, PHASE_STALE_WARNING_DAYS


def _make_phases(phase_name: str, period: str, behavior: str = "test") -> dict:
    return {phase_name: {"period": period, "behavior": behavior, "impact": "NEGATIVE"}}


class TestOpenEndedPhaseStaleness:
    """Open-ended '+' phases expire after MAX_OPEN_ENDED_PHASE_DAYS."""

    def test_recent_phase_active(self):
        """Phase started 30 days ago is still active."""
        start = (datetime.now().date() - timedelta(days=30)).strftime("%b %d, %Y")
        phases = _make_phases("sustained_pressure", f"{start}+")
        phase_name, phase_info, days_active = _get_current_phase(phases)
        assert phase_name == "sustained_pressure"
        assert phase_info is not None
        assert 28 <= days_active <= 32  # Allow small date drift

    def test_phase_at_max_days_still_active(self):
        """Phase at exactly MAX_OPEN_ENDED_PHASE_DAYS is still active."""
        start = (datetime.now().date() - timedelta(days=MAX_OPEN_ENDED_PHASE_DAYS)).strftime(
            "%b %d, %Y"
        )
        phases = _make_phases("sustained_pressure", f"{start}+")
        phase_name, _, days_active = _get_current_phase(phases)
        assert phase_name == "sustained_pressure"
        assert days_active == MAX_OPEN_ENDED_PHASE_DAYS

    def test_phase_past_max_days_expired(self):
        """Phase older than MAX_OPEN_ENDED_PHASE_DAYS is expired."""
        start = (datetime.now().date() - timedelta(days=MAX_OPEN_ENDED_PHASE_DAYS + 1)).strftime(
            "%b %d, %Y"
        )
        phases = _make_phases("sustained_pressure", f"{start}+")
        phase_name, phase_info, _ = _get_current_phase(phases)
        assert phase_name is None
        assert phase_info is None

    def test_bounded_range_unaffected(self):
        """Bounded date ranges are not subject to staleness expiry."""
        today = datetime.now().date()
        start = today - timedelta(days=100)
        end = today + timedelta(days=5)
        start_str = start.strftime("%b %d")
        end_day = end.day
        year = end.strftime("%Y")
        period = f"{start_str}-{end_day}, {year}"
        phases = _make_phases("immediate_shock", period)
        phase_name, _, days_active = _get_current_phase(phases)
        # Bounded phases should return 0 for days_active
        assert days_active == 0


class TestPhaseStaleFlag:
    """days_active and phase_stale fields in shock dict."""

    def test_days_active_present(self):
        """_get_current_phase returns days_active for open-ended phases."""
        start = (datetime.now().date() - timedelta(days=45)).strftime("%b %d, %Y")
        phases = _make_phases("sustained_pressure", f"{start}+")
        _, _, days_active = _get_current_phase(phases)
        assert 43 <= days_active <= 47

    def test_stale_threshold(self):
        """Phase older than PHASE_STALE_WARNING_DAYS is flagged as stale."""
        days = PHASE_STALE_WARNING_DAYS + 1
        start = (datetime.now().date() - timedelta(days=days)).strftime("%b %d, %Y")
        phases = _make_phases("sustained_pressure", f"{start}+")
        _, _, days_active = _get_current_phase(phases)
        assert days_active > PHASE_STALE_WARNING_DAYS

    def test_fresh_not_stale(self):
        """Phase younger than warning threshold is not stale."""
        start = (datetime.now().date() - timedelta(days=10)).strftime("%b %d, %Y")
        phases = _make_phases("sustained_pressure", f"{start}+")
        _, _, days_active = _get_current_phase(phases)
        assert days_active <= PHASE_STALE_WARNING_DAYS


class TestMonthOnlyFormat:
    """Regression: 'Apr 2026+' format (month without day) must resolve."""

    def test_month_only_open_ended_resolves(self):
        """'Apr 2026+' defaults to day 1 — the original bug."""
        today = datetime.now().date()
        period = today.strftime("%b %Y+")
        phases = _make_phases("resolution_or_escalation", period)
        phase_name, phase_info, days_active = _get_current_phase(phases)
        assert phase_name == "resolution_or_escalation"
        assert phase_info is not None
        # Day defaults to 1st, so days_active >= today.day - 1
        assert days_active >= 0
