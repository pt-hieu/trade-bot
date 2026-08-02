"""RecommendationOverride validator tests (2026-04-24 persistence contract).

Invariants:
  - `midday_status` is a strict Literal["CONFIRM","ADJUST","CANCEL"] —
    `"EXIT"` is rejected by Pydantic.
  - `CANCEL + reason mentions stop + revised_stop is None` → rejected by
    the model-level validator.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.midday import RecommendationOverride


def test_status_exit_is_rejected():
    with pytest.raises(ValidationError):
        RecommendationOverride(
            ticker="ACV",
            morning_action="HOLD",
            midday_status="EXIT",  # type: ignore[arg-type]
            reason="stop breached at 44.4k",
        )


def test_confirm_passes():
    override = RecommendationOverride(
        ticker="FPT",
        morning_action="HOLD",
        midday_status="CONFIRM",
        reason="Morning plan still valid",
    )
    assert override.midday_status == "CONFIRM"


def test_cancel_with_stop_and_revised_stop_passes():
    override = RecommendationOverride(
        ticker="ACV",
        morning_action="HOLD",
        midday_status="CANCEL",
        reason="Stop breached at 44.4k vs breakeven 44.91k",
        revised_stop=44910,
    )
    assert override.revised_stop == 44910


def test_cancel_with_stop_reason_without_revised_stop_rejected():
    with pytest.raises(ValidationError) as exc_info:
        RecommendationOverride(
            ticker="ACV",
            morning_action="HOLD",
            midday_status="CANCEL",
            reason="Stop breached at 44.4k",
            revised_stop=None,
        )
    assert "revised_stop" in str(exc_info.value)


def test_cancel_without_stop_reason_allows_null_stop():
    """Non-stop cancel reasons (DEFENSIVE, downtrend, etc.) don't require revised_stop."""
    override = RecommendationOverride(
        ticker="FPT",
        morning_action="BUY",
        midday_status="CANCEL",
        reason="DEFENSIVE stance — ADD/BUY blocked by deterministic gate",
    )
    assert override.revised_stop is None
