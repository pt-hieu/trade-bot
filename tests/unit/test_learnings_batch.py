"""Unit tests for batch-fetch learnings refactor."""

from collections import defaultdict
from unittest.mock import AsyncMock

import pytest

from retro_helpers.evaluation_loaders import (
    _group_by,
    batch_fetch_evaluations,
    batch_fetch_macro_evals,
    batch_fetch_midday,
    batch_fetch_rotation_evals,
    batch_fetch_violations,
)


class TestGroupBy:
    """Test the _group_by utility."""

    def test_groups_by_key(self):
        rows = [
            {"record_id": 1, "ticker": "FPT"},
            {"record_id": 1, "ticker": "VNM"},
            {"record_id": 2, "ticker": "HPG"},
        ]
        result = _group_by(rows, "record_id")
        assert len(result[1]) == 2
        assert len(result[2]) == 1
        assert result[1][0]["ticker"] == "FPT"

    def test_empty_rows(self):
        result = _group_by([], "record_id")
        assert result == defaultdict(list)

    def test_single_group(self):
        rows = [{"id": 5, "val": "a"}, {"id": 5, "val": "b"}]
        result = _group_by(rows, "id")
        assert len(result[5]) == 2

    def test_missing_record_returns_empty(self):
        rows = [{"record_id": 1, "data": "x"}]
        result = _group_by(rows, "record_id")
        assert result.get(999, []) == []


class TestBatchFetchEvaluations:
    @pytest.mark.asyncio
    async def test_groups_by_record_id(self):
        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = [
            {
                "record_id": 1,
                "ticker": "FPT",
                "recommendation": "BUY",
                "section": "core",
                "entry_hit": True,
                "stop_hit": False,
                "target_hit": False,
                "eod_price_vnd": 100000,
                "pnl_percent": 2.5,
                "status": "WON",
                "analysis": "",
                "won": True,
                "entry_gap_pct": 0.5,
                "predicted_rr": 3.0,
                "actual_max_rr": 2.0,
                "stop_buffer_pct": 1.0,
                "stop_vs_atr_ratio": 0.8,
                "atr_pct": 2.0,
                "day_change": 1.5,
                "trade_executed": True,
                "actual_pl_pct": 2.5,
                "actual_exit_price_vnd": 102500,
                "actual_pl_net_vnd": 250000,
                "strategy": "breakout",
            },
            {
                "record_id": 2,
                "ticker": "HPG",
                "recommendation": "HOLD",
                "section": "watch",
                "entry_hit": False,
                "stop_hit": False,
                "target_hit": False,
                "eod_price_vnd": 50000,
                "pnl_percent": None,
                "status": "PENDING",
                "analysis": "",
                "won": None,
                "entry_gap_pct": None,
                "predicted_rr": None,
                "actual_max_rr": None,
                "stop_buffer_pct": None,
                "stop_vs_atr_ratio": None,
                "atr_pct": None,
                "day_change": -0.5,
                "trade_executed": False,
                "actual_pl_pct": None,
                "actual_exit_price_vnd": None,
                "actual_pl_net_vnd": None,
                "strategy": None,
            },
        ]

        result = await batch_fetch_evaluations(mock_db, [1, 2])
        assert len(result[1]) == 1
        assert result[1][0]["ticker"] == "FPT"
        assert len(result[2]) == 1
        assert result.get(999, []) == []


class TestBatchFetchViolations:
    @pytest.mark.asyncio
    async def test_groups_violations(self):
        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = [
            {"record_id": 1, "violation_text": "BUY in DEFENSIVE mode"},
            {"record_id": 1, "violation_text": "Exceeded position size"},
        ]

        result = await batch_fetch_violations(mock_db, [1, 2])
        assert len(result[1]) == 2
        assert result.get(2, []) == []


class TestBatchFetchMidday:
    @pytest.mark.asyncio
    async def test_returns_first_row_per_record(self):
        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = [
            {"record_id": 1, "trading_mode": "NORMAL", "entries_hit": 2, "afternoon_plan": "hold"},
            {"record_id": 2, "trading_mode": "DEFENSIVE", "entries_hit": 0, "afternoon_plan": None},
        ]

        result = await batch_fetch_midday(mock_db, [1, 2])
        assert result[1]["trading_mode"] == "NORMAL"
        assert result[2]["entries_hit"] == 0
        assert 3 not in result


class TestBatchFetchRotationEvals:
    @pytest.mark.asyncio
    async def test_rotation_with_sector_returns(self):
        mock_db = AsyncMock()
        # First call: rotation_evaluations, second call: sector_returns
        mock_db.fetch_all.side_effect = [
            [
                {
                    "id": 10,
                    "record_id": 1,
                    "market_regime": "BULL",
                    "hot_avg_return": 3.5,
                    "cold_avg_return": -1.2,
                    "market_avg_return": 1.0,
                    "hot_vs_market": 2.5,
                    "cold_vs_market": -2.2,
                    "hot_hit_rate": 0.8,
                    "cold_hit_rate": 0.6,
                    "overall_accuracy": 0.7,
                    "rotation_effective": True,
                    "hot_sectors": ["Banking"],
                    "cold_sectors": ["Real Estate"],
                },
            ],
            [
                {"record_id": 1, "sector_name": "Banking", "return_pct": 3.5},
                {"record_id": 1, "sector_name": "Real Estate", "return_pct": -1.2},
            ],
        ]

        result = await batch_fetch_rotation_evals(mock_db, [1])
        assert 1 in result
        assert result[1]["market_regime"] == "BULL"
        assert result[1]["sector_returns"]["Banking"] == 3.5
        assert result[1]["hot_sectors"] == ["Banking"]

    @pytest.mark.asyncio
    async def test_no_rotation_data(self):
        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = []

        result = await batch_fetch_rotation_evals(mock_db, [1])
        assert result == {}


class TestBatchFetchMacroEvals:
    @pytest.mark.asyncio
    async def test_macro_with_null_values(self):
        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = [
            {
                "record_id": 1,
                "global_risk_regime": "CALM",
                "dxy_value": None,
                "vix_value": 18.5,
                "vn_index_change_pct": None,
                "regime_appropriate": True,
                "foreign_flow_aligned": True,
                "recommendation_compliance": True,
            },
        ]

        result = await batch_fetch_macro_evals(mock_db, [1])
        assert result[1]["dxy_value"] is None
        assert result[1]["vix_value"] == 18.5
        assert result[1]["vn_index_change_pct"] is None


class TestLoadLearningsQueryCount:
    """Verify the refactored function makes exactly 9 DB calls (1 initial + 8 batch)."""

    @pytest.mark.asyncio
    async def test_query_count_with_records(self, mock_trading_config):
        mock_db = AsyncMock()

        # Call sequence: 1 initial daily_records + 8 batch fetches
        daily_records = [
            {
                "id": i,
                "record_date": f"2026-03-{i:02d}",
                "total_recs": 3,
                "entry_hit_rate": 0.5,
                "win_rate": 0.6,
                "best_call": "FPT",
                "worst_call": "VNM",
                "key_insight": "test",
                "trading_mode": "NORMAL",
                "mode_compliance": True,
            }
            for i in range(1, 6)
        ]

        # Return daily_records for first call, empty lists for batch calls
        mock_db.fetch_all.side_effect = [
            daily_records,  # initial query
            [],  # evaluations
            [],  # recommendations
            [],  # violations
            [],  # midday
            [],  # midday_summaries
            [],  # rotation_evaluations (returns empty → skips sector_returns)
            [],  # macro_evaluations
        ]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("shared.database.get_db", AsyncMock(return_value=mock_db))

            from retro_helpers.learnings import load_learnings_from_db

            result = await load_learnings_from_db(days=30)

        # 1 initial + 7 batch (rotation empty so no sector_returns call) = 8
        assert mock_db.fetch_all.call_count == 8
        assert result["summary"]["total_days"] == 5

    @pytest.mark.asyncio
    async def test_empty_records_returns_scaffold(self):
        mock_db = AsyncMock()
        mock_db.fetch_all.return_value = []

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("shared.database.get_db", AsyncMock(return_value=mock_db))

            from retro_helpers.learnings import load_learnings_from_db

            result = await load_learnings_from_db(days=30)

        assert mock_db.fetch_all.call_count == 1  # only initial query
        assert result["summary"]["total_days"] == 0
        assert result["daily_records"] == []
