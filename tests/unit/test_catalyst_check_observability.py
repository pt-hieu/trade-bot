"""SWI-57: catalyst_check spike disposition Logfire probe."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch


def test_no_spike_emits_disposition():
    from shared import observability

    with patch.object(observability, "log_info") as mock_log:
        observability.log_info(
            "catalyst_check_spike_disposition",
            disposition="no_spike",
            trigger="",
            has_spike=False,
            scan_date=str(date(2026, 5, 3)),
        )
    assert mock_log.called
    args, kwargs = mock_log.call_args
    assert args[0] == "catalyst_check_spike_disposition"
    assert kwargs["disposition"] == "no_spike"
    assert kwargs["has_spike"] is False


def test_revised_disposition_carries_trigger():
    from shared import observability

    with patch.object(observability, "log_info") as mock_log:
        observability.log_info(
            "catalyst_check_spike_disposition",
            disposition="revised",
            trigger="News spike: M&A deal",
            has_spike=True,
            scan_date="2026-05-03",
        )
    _, kwargs = mock_log.call_args
    assert kwargs["disposition"] == "revised"
    assert kwargs["trigger"] == "News spike: M&A deal"


def test_suppressed_outside_active_hours_disposition():
    from shared import observability

    with patch.object(observability, "log_info") as mock_log:
        observability.log_info(
            "catalyst_check_spike_disposition",
            disposition="suppressed_outside_active_hours",
            trigger="t",
            has_spike=True,
            scan_date="2026-05-03",
        )
    _, kwargs = mock_log.call_args
    assert kwargs["disposition"] == "suppressed_outside_active_hours"
    assert kwargs["has_spike"] is True
