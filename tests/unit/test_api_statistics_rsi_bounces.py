"""Unit tests for shared/api/statistics.get_rsi_oversold_bounces."""

import pytest

from tests.unit._fixtures.api_statistics import (
    _mock_ohlcv_result,
    _mock_rsi_result,
    _ohlcv,
    _patch_stats,
    _rsi_record,
)


class TestGetRsiOversoldBounces:
    @pytest.mark.asyncio
    async def test_detects_bounces_correctly(self):
        """Days with RSI < 30 and next-day positive change count as bounces."""
        # Arrange: day 1 RSI=25 (oversold), day 2 close is higher → bounce
        ohlcv = [
            _ohlcv("2026-02-01", 90.0),  # RSI=25 → qualifies; next day=95 → bounce
            _ohlcv("2026-02-02", 95.0),  # RSI=28 → qualifies; next day=92 → no bounce
            _ohlcv("2026-02-03", 92.0),  # RSI=35 → does not qualify
            _ohlcv("2026-02-04", 94.0),
        ]
        rsi_records = [
            _rsi_record("2026-02-01", 25.0),
            _rsi_record("2026-02-02", 28.0),
            _rsi_record("2026-02-03", 35.0),
            _rsi_record("2026-02-04", 38.0),
        ]

        # Act
        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_rsi_oversold_bounces

            result = await get_rsi_oversold_bounces("TCB", rsi_threshold=30.0, days_back=90)

        # Assert
        assert result["total_occurrences"] == 2
        assert result["bounce_rate"] == 0.5  # 1 bounce out of 2

    @pytest.mark.asyncio
    async def test_no_bounces_when_rsi_stays_high(self):
        """No qualifying days when RSI never drops below threshold."""
        ohlcv = [_ohlcv(f"2026-02-{i + 1:02d}", 100.0) for i in range(5)]
        rsi_records = [_rsi_record(f"2026-02-{i + 1:02d}", 50.0 + i) for i in range(5)]

        # Act
        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_rsi_oversold_bounces

            result = await get_rsi_oversold_bounces("TCB", rsi_threshold=30.0, days_back=90)

        # Assert
        assert result["total_occurrences"] == 0
        assert result["bounce_rate"] == 0

    @pytest.mark.asyncio
    async def test_no_ticker_returns_empty_stats(self):
        """Without ticker, returns zero stats (cross-ticker requires DB)."""
        from shared.api.statistics import get_rsi_oversold_bounces

        result = await get_rsi_oversold_bounces(ticker=None)
        assert result["total_occurrences"] == 0
        assert result["bounce_rate"] == 0

    @pytest.mark.asyncio
    async def test_handles_empty_ohlcv(self):
        """Returns zero stats when API returns no OHLCV data."""
        with _patch_stats(
            {"TCB": {"data": [], "count": 0}},
            _mock_rsi_result([]),
        ):
            from shared.api.statistics import get_rsi_oversold_bounces

            result = await get_rsi_oversold_bounces("TCB", days_back=90)

        assert result["total_occurrences"] == 0

    @pytest.mark.asyncio
    async def test_consecutive_streak_detection(self):
        """Detects max consecutive oversold days correctly."""
        # 3 consecutive oversold days
        ohlcv = [_ohlcv(f"2026-02-{i + 1:02d}", 90.0 - i) for i in range(5)]
        rsi_records = [
            _rsi_record("2026-02-01", 28.0),
            _rsi_record("2026-02-02", 25.0),
            _rsi_record("2026-02-03", 22.0),  # 3 consecutive
            _rsi_record("2026-02-04", 35.0),  # break
            _rsi_record("2026-02-05", 40.0),
        ]

        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_rsi_oversold_bounces

            result = await get_rsi_oversold_bounces("TCB", rsi_threshold=30.0, days_back=90)

        assert result["max_consecutive_oversold"] == 3
