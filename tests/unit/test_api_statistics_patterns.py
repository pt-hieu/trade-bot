"""Unit tests for shared/api/statistics: pattern outcome + consecutive pattern days."""

import pytest

from tests.unit._fixtures.api_statistics import (
    _mock_ohlcv_result,
    _mock_rsi_result,
    _ohlcv,
    _ohlcv_at_low,
    _patch_stats,
    _rsi_record,
)


class TestGetPatternOutcomeStats:
    @pytest.mark.asyncio
    async def test_no_ticker_returns_empty_stats(self):
        """Without ticker, returns empty stats."""
        from shared.api.statistics import get_pattern_outcome_stats

        result = await get_pattern_outcome_stats("hammer", ticker=None)
        assert result["occurrences"] == 0
        assert result["win_rate"] == 0

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_pattern_matches(self):
        """When no days match the pattern, returns zero stats."""
        # Arrange: all records are doji-like (body < 1% range)
        ohlcv = [
            {
                "time": f"2026-02-{i + 1:02d}",
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.0,  # doji (open == close)
                "volume": 1_000_000,
            }
            for i in range(5)
        ]
        rsi_records = [_rsi_record(f"2026-02-{i + 1:02d}", 50.0) for i in range(5)]

        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_pattern_outcome_stats

            # Looking for hammer but only doji exists
            result = await get_pattern_outcome_stats("hammer", ticker="TCB")

        assert result["occurrences"] == 0

    @pytest.mark.asyncio
    async def test_respects_rsi_filter(self):
        """RSI range filter excludes days outside [rsi_min, rsi_max]."""
        # Build a hammer candle on day 3 with RSI=60 (above rsi_max=50)
        hammer = {
            "time": "2026-02-03",
            "open": 100.0,
            "high": 101.0,
            "low": 96.0,  # long lower wick
            "close": 100.5,
            "volume": 1_000_000,
        }
        ohlcv = [
            _ohlcv("2026-02-01", 102.0),
            _ohlcv("2026-02-02", 100.0),
            hammer,
            _ohlcv("2026-02-04", 101.0),
        ]
        rsi_records = [
            _rsi_record("2026-02-01", 55.0),
            _rsi_record("2026-02-02", 58.0),
            _rsi_record("2026-02-03", 60.0),  # RSI=60 outside rsi_max=50
            _rsi_record("2026-02-04", 55.0),
        ]

        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_pattern_outcome_stats

            result = await get_pattern_outcome_stats("hammer", rsi_max=50, ticker="TCB")

        # RSI=60 filtered out → no matches
        assert result["occurrences"] == 0


class TestGetConsecutivePatternDays:
    @pytest.mark.asyncio
    async def test_detects_rsi_below_30_streak(self):
        """Detects max consecutive streak of RSI < 30.

        Gap threshold is ≤3 days (covers Mon–Fri weekends). Use > 3 day gap to
        separate two distinct streaks.
        """
        # Streak A: 02-02, 02-03, 02-04 (3 days)
        # Gap: 02-04 → 02-09 = 5 days (exceeds 3-day threshold → separate streak)
        # Streak B: 02-09 (1 day)
        dates = [
            "2026-02-01",
            "2026-02-02",
            "2026-02-03",
            "2026-02-04",
            "2026-02-05",
            "2026-02-09",
            "2026-02-10",
        ]
        ohlcv = [_ohlcv(d, 90.0) for d in dates]
        rsi_records = [
            _rsi_record("2026-02-01", 35.0),
            _rsi_record("2026-02-02", 28.0),  # streak A start
            _rsi_record("2026-02-03", 25.0),
            _rsi_record("2026-02-04", 22.0),  # streak A end (len=3)
            _rsi_record("2026-02-05", 40.0),  # not oversold
            _rsi_record("2026-02-09", 27.0),  # streak B (5-day gap from 02-04)
            _rsi_record("2026-02-10", 35.0),
        ]

        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_consecutive_pattern_days

            result = await get_consecutive_pattern_days("TCB", "rsi_below_30", days_back=90)

        assert result["max_consecutive"] == 3
        assert result["total_days"] == 4

    @pytest.mark.asyncio
    async def test_detects_closed_at_low_streak(self):
        """Detects streak of closed_at_low days."""
        ohlcv = [
            _ohlcv("2026-02-01", 100.0),
            _ohlcv_at_low("2026-02-02", 98.0),  # streak 1
            _ohlcv_at_low("2026-02-03", 96.0),  # streak 2
            _ohlcv("2026-02-04", 97.0),  # break
            _ohlcv("2026-02-05", 99.0),
        ]
        rsi_records = [_rsi_record(f"2026-02-{i + 1:02d}", 50.0) for i in range(5)]

        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_consecutive_pattern_days

            result = await get_consecutive_pattern_days("TCB", "closed_at_low", days_back=90)

        assert result["max_consecutive"] == 2

    @pytest.mark.asyncio
    async def test_no_qualifying_days_returns_zero(self):
        """Returns zero when condition never met."""
        ohlcv = [_ohlcv(f"2026-02-{i + 1:02d}", 100.0) for i in range(5)]
        rsi_records = [_rsi_record(f"2026-02-{i + 1:02d}", 50.0) for i in range(5)]

        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_consecutive_pattern_days

            result = await get_consecutive_pattern_days("TCB", "rsi_below_30", days_back=90)

        assert result["total_days"] == 0
        assert result["max_consecutive"] == 0
        assert result["current_streak"] == 0

    @pytest.mark.asyncio
    async def test_unknown_condition_returns_error(self):
        """Returns error dict for unknown condition string."""
        from shared.api.statistics import get_consecutive_pattern_days

        result = await get_consecutive_pattern_days("TCB", "unknown_condition", days_back=90)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_distribution_computed_correctly(self):
        """Distribution maps streak_length → count.

        Gap threshold is ≤3 days. Use 5-day gaps to ensure separate streaks:
        - Streak A: 02-01 (len=1)
        - Streak B: 02-06, 02-07 (len=2)   [5 days from 02-01]
        - Streak C: 02-12 (len=1)           [5 days from 02-07]
        """
        dates = [f"2026-02-{i:02d}" for i in range(1, 14)]
        ohlcv = [_ohlcv(d, 90.0) for d in dates]
        rsi_records = [
            _rsi_record("2026-02-01", 28.0),  # streak A (len=1)
            _rsi_record("2026-02-02", 40.0),
            _rsi_record("2026-02-03", 40.0),
            _rsi_record("2026-02-04", 40.0),
            _rsi_record("2026-02-05", 40.0),
            _rsi_record("2026-02-06", 25.0),  # streak B start (5d gap from 02-01)
            _rsi_record("2026-02-07", 27.0),  # streak B end (len=2)
            _rsi_record("2026-02-08", 40.0),
            _rsi_record("2026-02-09", 40.0),
            _rsi_record("2026-02-10", 40.0),
            _rsi_record("2026-02-11", 40.0),
            _rsi_record("2026-02-12", 26.0),  # streak C (5d gap from 02-07, len=1)
            _rsi_record("2026-02-13", 40.0),
        ]

        with _patch_stats(
            _mock_ohlcv_result("TCB", ohlcv),
            _mock_rsi_result(rsi_records),
        ):
            from shared.api.statistics import get_consecutive_pattern_days

            result = await get_consecutive_pattern_days("TCB", "rsi_below_30", days_back=90)

        assert result["distribution"][1] == 2  # two streaks of length 1
        assert result["distribution"][2] == 1  # one streak of length 2
        assert result["max_consecutive"] == 2
