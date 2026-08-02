"""Unit tests for data/technicals.py: swing point detection + candlestick patterns + fallback."""

import pandas as pd

from data.technicals import detect_candlestick_patterns, detect_swing_points


class TestDetectSwingPoints:
    """Tests for detect_swing_points function."""

    def test_detects_swing_high(self):
        df = pd.DataFrame(
            {
                "high": [10, 11, 12, 13, 14, 20, 14, 13, 12, 11, 10],
                "low": [9, 10, 11, 12, 13, 19, 13, 12, 11, 10, 9],
                "time": pd.date_range("2026-01-01", periods=11),
            }
        )

        result = detect_swing_points(df, window=2)

        assert "swing_high" in result
        assert result["swing_high"] == 20.0

    def test_detects_swing_low(self):
        df = pd.DataFrame(
            {
                "high": [20, 18, 16, 14, 12, 10, 12, 14, 16, 18, 20],
                "low": [19, 17, 15, 13, 11, 5, 11, 13, 15, 17, 19],
                "time": pd.date_range("2026-01-01", periods=11),
            }
        )

        result = detect_swing_points(df, window=2)

        assert "swing_low" in result
        assert result["swing_low"] == 5.0

    def test_empty_on_insufficient_data(self):
        df = pd.DataFrame(
            {
                "high": [10, 12, 15],
                "low": [9, 11, 14],
                "time": pd.date_range("2026-01-01", periods=3),
            }
        )

        result = detect_swing_points(df, window=5)

        assert result == {}

    def test_handles_date_index_instead_of_column(self):
        df = pd.DataFrame(
            {
                "high": [10, 11, 12, 13, 14, 20, 14, 13, 12, 11, 10],
                "low": [9, 10, 11, 12, 13, 19, 13, 12, 11, 10, 9],
            },
            index=pd.date_range("2026-01-01", periods=11),
        )

        result = detect_swing_points(df, window=2)

        assert "swing_high" in result


class TestDetectCandlestickPatterns:
    """Tests for candlestick pattern detection."""

    def test_detects_hammer(self):
        df = pd.DataFrame(
            {
                "open": [100, 100, 99],
                "high": [105, 105, 100],
                "low": [95, 95, 90],
                "close": [104, 104, 99.5],
            }
        )

        result = detect_candlestick_patterns(df)

        assert result["pattern"] == "hammer"
        assert result["signal"] == "bullish_reversal"

    def test_detects_inverted_hammer(self):
        df = pd.DataFrame(
            {
                "open": [100, 100, 91],
                "high": [105, 105, 100],
                "low": [95, 95, 90],
                "close": [104, 104, 91.5],
            }
        )

        result = detect_candlestick_patterns(df)

        assert result["pattern"] == "inverted_hammer"
        assert result["signal"] == "bullish_reversal"

    def test_detects_doji(self):
        df = pd.DataFrame(
            {
                "open": [100, 100, 100.0],
                "high": [105, 105, 105],
                "low": [95, 95, 95],
                "close": [104, 104, 100.0],
            }
        )

        result = detect_candlestick_patterns(df)

        assert result["pattern"] == "doji"
        assert result["signal"] == "indecision"

    def test_detects_bullish_engulfing(self):
        df = pd.DataFrame(
            {
                "open": [100, 102, 95],
                "high": [105, 103, 108],
                "low": [95, 98, 94],
                "close": [104, 99, 107],
            }
        )

        result = detect_candlestick_patterns(df)

        assert result["pattern"] == "bullish_engulfing"
        assert result["signal"] == "bullish_reversal"

    def test_detects_bearish_engulfing(self):
        df = pd.DataFrame(
            {
                "open": [100, 98, 107],
                "high": [105, 103, 108],
                "low": [95, 97, 94],
                "close": [104, 101, 95],
            }
        )

        result = detect_candlestick_patterns(df)

        assert result["pattern"] == "bearish_engulfing"
        assert result["signal"] == "bearish_reversal"

    def test_no_pattern_on_normal_candle(self):
        df = pd.DataFrame(
            {
                "open": [100, 100, 100],
                "high": [105, 105, 105],
                "low": [95, 95, 95],
                "close": [103, 103, 103],
            }
        )

        result = detect_candlestick_patterns(df)

        assert result["pattern"] is None
        assert result["signal"] is None

    def test_handles_insufficient_data(self):
        df = pd.DataFrame(
            {"open": [100, 101], "high": [105, 106], "low": [95, 96], "close": [103, 104]}
        )

        result = detect_candlestick_patterns(df)

        assert result["pattern"] is None

    def test_handles_zero_range(self):
        df = pd.DataFrame(
            {
                "open": [100, 100, 100],
                "high": [100, 100, 100],
                "low": [100, 100, 100],
                "close": [100, 100, 100],
            }
        )

        result = detect_candlestick_patterns(df)

        assert result["pattern"] is None


class TestSwingPointFallback:
    """Tests for provisional swing point fallback when price breaks detected swings."""

    def test_swing_low_fallback_on_crash(self):
        """When price crashes below detected swing_low, use recent low as provisional."""
        highs = [120, 118, 116, 112, 108, 102, 108, 112, 116, 118, 120, 115, 110, 100, 95, 92]
        lows = [118, 116, 114, 110, 106, 100, 106, 110, 114, 116, 118, 113, 108, 98, 93, 90]

        df = pd.DataFrame(
            {
                "high": highs,
                "low": lows,
                "time": pd.date_range("2026-01-15", periods=len(highs)),
            }
        )

        result = detect_swing_points(df, window=5)

        assert "swing_low" in result
        assert result["swing_low"] <= 93.0

    def test_swing_high_fallback_on_breakout(self):
        """When price breaks above detected swing_high, use recent high as provisional."""
        lows = [90, 92, 94, 96, 98, 100, 98, 96, 94, 92, 90, 95, 100, 105, 110, 115]
        highs = [92, 94, 96, 98, 100, 102, 100, 98, 96, 94, 92, 97, 102, 107, 112, 117]

        df = pd.DataFrame(
            {
                "high": highs,
                "low": lows,
                "time": pd.date_range("2026-01-15", periods=len(highs)),
            }
        )

        result = detect_swing_points(df, window=5)

        assert "swing_high" in result
        assert result["swing_high"] >= 112.0

    def test_no_fallback_when_within_range(self):
        df = pd.DataFrame(
            {
                "high": [20, 18, 16, 14, 12, 10, 12, 14, 16, 18, 15],
                "low": [19, 17, 15, 13, 11, 5, 11, 13, 15, 17, 14],
                "time": pd.date_range("2026-01-01", periods=11),
            }
        )

        result = detect_swing_points(df, window=2)

        assert result["swing_low"] == 5.0
