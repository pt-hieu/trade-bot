"""Test evaluator's retry-path guard against silent zero-eval persistence.

Group 3b: when recommendations is empty BUT the DB shows morning recs > 0,
evaluate_day_with_agent must raise RETRO_EMPTY_RECS_ON_RETRY rather than
returning _empty_result and letting daily.py silently persist zero rows.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_empty_recs_with_db_morning_recs_raises():
    scan = date(2026, 4, 19)
    db_recs = [{"ticker": "FPT", "action": "HOLD"}]

    with patch(
        "shared.neon.insert_records.get_morning_recommendations",
        new=AsyncMock(return_value=db_recs),
    ):
        from agents.retro.evaluator import evaluate_day_with_agent

        with pytest.raises(RuntimeError, match="RETRO_EMPTY_RECS_ON_RETRY"):
            await evaluate_day_with_agent([], scan_date=scan)


@pytest.mark.asyncio
async def test_empty_recs_with_empty_db_returns_empty_result():
    scan = date(2026, 4, 19)

    with patch(
        "shared.neon.insert_records.get_morning_recommendations",
        new=AsyncMock(return_value=[]),
    ):
        from agents.retro.evaluator import evaluate_day_with_agent

        result = await evaluate_day_with_agent([], scan_date=scan)
    assert result["evaluations"] == []
    assert result["day_summary"]["total_recs"] == 0
