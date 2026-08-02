"""Phase-5 systemic re-raise + per-pick scoping (SWI-248).

A systemic failure in the alert-registration tree must fail the phase loudly
rather than collapsing Phase 5 to 0 rows while the pipeline stays green
(`report_caught` logs a span and returns None). A malformed individual pick is
NOT systemic — it is scoped per-row and must not propagate.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_registration_exception_propagates():
    from pipeline.phase_alerts import run_phase5_alert_pipeline

    with (
        patch(
            "pipeline.phase_alerts._fetch_alert_prices",
            new=AsyncMock(return_value={"FPT": 100000.0}),
        ),
        patch(
            "pipeline.phase_alerts.run_alert_registration",
            new=AsyncMock(side_effect=RuntimeError("simulated registration failure")),
        ),
        pytest.raises(RuntimeError, match="simulated registration failure"),
    ):
        await run_phase5_alert_pipeline(
            position_alerts={"alerts": []},
            pre_computed_picks=[],
            scan_date=date(2026, 5, 30),
            global_risk_regime="CALM",
            trading_mode="NORMAL",
            holdings=[],
            skip_alerts=False,
        )


@pytest.mark.asyncio
async def test_per_pick_none_does_not_propagate():
    from agents.alert_registrar.deterministic import register_picks_as_alerts

    with patch(
        "agents.alert_registrar.deterministic.db_register_alert",
        new=AsyncMock(return_value=1),
    ):
        count = await register_picks_as_alerts(
            pre_computed_picks=[None],
            source="morning_brief",
            scan_date=date(2026, 5, 30),
            current_prices={},
        )

    assert count == 0  # the None pick is scoped, not raised
