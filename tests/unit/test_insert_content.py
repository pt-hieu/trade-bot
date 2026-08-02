"""Tests for insert_content.py — midday check insert with verification."""

import logging
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from shared.neon.insert_content import insert_midday_check


@pytest.fixture
def mock_db():
    """Mock database with all needed methods."""
    db = AsyncMock()
    db.fetch_val = AsyncMock(return_value=1)
    db.execute = AsyncMock()
    return db


@pytest.fixture
def midday_data():
    """Sample midday check data."""
    return {
        "trading_mode": "NORMAL",
        "morning_reflection": "Market stable",
        "afternoon_plan": [
            {
                "ticker": None,
                "action": "NOTE",
                "confidence": "LOW",
                "reason": "Hold positions",
            }
        ],
        "capital_note": None,
        "recommendation_overrides": [],
        "entries_hit": [
            {"ticker": "FPT", "recommended_entry": 99.0, "actual_low": 98.5, "status": "HIT"},
        ],
        "big_movers": [
            {
                "ticker": "VHM",
                "open_price": 95.0,
                "current_price": 100.0,
                "change_pct": 5.26,
                "direction": "UP",
            },
        ],
        "position_alerts": [
            {
                "ticker": "TCB",
                "current_price": 35.0,
                "level": 34.0,
                "level_type": "stop",
                "distance_pct": 2.9,
                "urgency": "LOW",
            },
        ],
    }


class TestInsertMiddayCheck:
    @pytest.mark.asyncio
    async def test_returns_true_on_successful_insert(self, mock_db, midday_data):
        scan = date(2026, 3, 6)
        # fetch_val returns midday_id=1 for INSERT, then counts for verification
        mock_db.fetch_val = AsyncMock(side_effect=[1, 1, 1, 1])

        with patch("shared.neon.insert_midday.get_db", return_value=mock_db):
            result = await insert_midday_check(scan, midday_data)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_and_logs_on_exception(self, mock_db, midday_data, caplog):
        scan = date(2026, 3, 6)
        mock_db.fetch_val = AsyncMock(side_effect=Exception("connection lost"))

        with (
            patch("shared.neon.insert_midday.get_db", return_value=mock_db),
            caplog.at_level(logging.WARNING),
        ):
            result = await insert_midday_check(scan, midday_data)

        assert result is False
        assert "insert_midday_check 2026-03-06" in caplog.text
        assert "connection lost" in caplog.text

    @pytest.mark.asyncio
    async def test_logs_warning_when_expected_rows_but_zero_written(
        self, mock_db, midday_data, caplog
    ):
        scan = date(2026, 3, 6)
        # fetch_val: midday_id=1, then 0 for all 3 child count queries
        mock_db.fetch_val = AsyncMock(side_effect=[1, 0, 0, 0])

        with (
            patch("shared.neon.insert_midday.get_db", return_value=mock_db),
            caplog.at_level(logging.WARNING),
        ):
            result = await insert_midday_check(scan, midday_data)

        assert result is True  # still returns True (main row inserted)
        assert "expected 3 child rows, wrote 0" in caplog.text

    @pytest.mark.asyncio
    async def test_rejects_invalid_ticker_in_entries(self, mock_db):
        """Sector labels like LOGISTICS should be filtered out."""
        scan = date(2026, 3, 6)
        data = {
            "entries_hit": [{"ticker": "LOGISTICS", "status": "HIT"}],
            "big_movers": [],
            "position_alerts": [],
        }
        mock_db.fetch_val = AsyncMock(return_value=1)

        with patch("shared.neon.insert_midday.get_db", return_value=mock_db):
            result = await insert_midday_check(scan, data)

        assert result is True
        # No child INSERT should have been called (only DELETEs)
        insert_calls = [
            c for c in mock_db.execute.call_args_list if "INSERT INTO midday_entries_hit" in str(c)
        ]
        assert len(insert_calls) == 0
