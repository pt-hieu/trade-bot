"""SWI-255: midday override reason must use signal language, not outcome verbs."""

from __future__ import annotations

from datetime import date

import pytest

from agents.midday.validate import validate_midday_overrides
from shared.neon.insert_midday import (
    MiddayOverrideReasonViolation,
    _enforce_midday_override_reason_signal_language,
)


def test_agent_validator_flags_outcome_verb():
    result = validate_midday_overrides(
        [{"ticker": "ACV", "reason": "position closed per stop-loss discipline"}]
    )
    assert not result.passed
    assert any(v.check == "OVERRIDE_REASON_OUTCOME_VERB" for v in result.violations)


def test_agent_validator_passes_signal_language():
    result = validate_midday_overrides(
        [{"ticker": "ACV", "reason": "signal cancelled — stop level breached intraday"}]
    )
    assert result.passed


def test_db_boundary_gate_rejects_outcome_verb():
    with pytest.raises(MiddayOverrideReasonViolation):
        _enforce_midday_override_reason_signal_language(
            date(2026, 5, 5),
            {"ticker": "ACV", "reason": "ACV exit executed at stop"},
        )


def test_db_boundary_gate_accepts_signal_language():
    _enforce_midday_override_reason_signal_language(
        date(2026, 5, 5),
        {"ticker": "ACV", "reason": "stop level breached intraday — signal cancelled"},
    )
