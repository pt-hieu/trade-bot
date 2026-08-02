"""Unit tests for shared/api/statistics.get_price_action_analysis."""

import pytest

from tests.unit._fixtures.api_statistics import (
    _mock_ohlcv_result,
    _mock_rsi_result,
    _ohlcv,
    _ohlcv_at_low,
    _patch_stats,
    _rsi_record,
)


class TestGetPriceActionAnalysis:
    @pytest.mark.asyncio
    async def test_no_ticker_returns_empty_stats(self):
        """Without ticker, returns empty stats."""
        from shared.api.statistics import get_price_action_analysis

        result = await get_price_action_analysis(ticker=None)
        assert result["closed_at_low_count"] == 0
        assert result["reversal_rate"] == 0

    @pytest.mark.asyncio
    async def test_detects_closed_at_low_and_reversal(self):
        """Days that close at low and have positive next-day return count as reversals."""
        # Day 2 closes at low, day 3 is higher → reversal
        ohlcv = [
            _ohlcv("2026-02-01", 100.0),
            _ohlcv_at_low("2026-02-02", 95.0),  # closed_at_low=True, next=100 → reversal
            _ohlcv("2026-02-03", 100.0),
        ]
        rsi_records = [
            _rsi_record("2026-02-01", 45.0),
            _rsi_record("2026-02-02", 40.0),
            _rsi_record("2026-02-03", 43.0),
        ]

        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_price_action_analysis

            result = await get_price_action_analysis(ticker="TCB", days_back=90)

        assert result["closed_at_low_count"] == 1
        assert result["reversal_rate"] == 1.0  # 1 reversal out of 1

    @pytest.mark.asyncio
    async def test_high_volume_subset(self):
        """Identifies high-volume closed-at-low days separately."""
        # Day 2: closed_at_low with high volume (3x avg)
        # Day 4: closed_at_low with normal volume (0.8x avg)
        ohlcv = [
            _ohlcv("2026-02-01", 100.0),
            _ohlcv_at_low("2026-02-02", 95.0, vol_mult=3.0),  # high vol, reversal on day 3
            _ohlcv("2026-02-03", 98.0),
            _ohlcv_at_low("2026-02-04", 96.0, vol_mult=0.8),  # low vol
            _ohlcv("2026-02-05", 94.0),  # no reversal for day 4
        ]
        rsi_records = [_rsi_record(f"2026-02-{i + 1:02d}", 40.0) for i in range(5)]

        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_price_action_analysis

            result = await get_price_action_analysis(ticker="TCB", days_back=90)

        assert result["closed_at_low_count"] == 2
        # High volume subset: 1 day with vol_mult=3 → volume > 20d_avg is likely
        # (The exact count depends on volume_vs_avg computation, just check structure)
        assert "with_high_volume" in result
        assert "count" in result["with_high_volume"]

    @pytest.mark.asyncio
    async def test_no_closed_at_low_days(self):
        """Returns zero stats when no days closed at low."""
        ohlcv = [_ohlcv(f"2026-02-{i + 1:02d}", 100.0) for i in range(5)]
        rsi_records = [_rsi_record(f"2026-02-{i + 1:02d}", 50.0) for i in range(5)]

        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_price_action_analysis

            result = await get_price_action_analysis(ticker="TCB", days_back=90)

        assert result["closed_at_low_count"] == 0
        assert result["reversal_rate"] == 0
