"""Unit tests for data/technicals.py: classify_trend + generate_analysis_text."""

import pandas as pd

from data.technicals import classify_trend, generate_analysis_text


class TestClassifyTrend:
    """Tests for trend classification."""

    def test_uptrend_detection(self):
        df = pd.DataFrame(
            {
                "close": [100, 102, 104, 106, 110],
                "open": [99, 101, 103, 105, 107],
            }
        )
        result = classify_trend(df, ma20=105, ma50=100)
        assert result["trend"] == "UPTREND"

    def test_downtrend_detection(self):
        df = pd.DataFrame(
            {
                "close": [100, 98, 96, 94, 90],
                "open": [101, 99, 97, 95, 93],
            }
        )
        result = classify_trend(df, ma20=95, ma50=100)
        assert result["trend"] == "DOWNTREND"

    def test_sideways_detection(self):
        df = pd.DataFrame(
            {
                "close": [100, 101, 99, 100, 98],
                "open": [99, 100, 100, 99, 101],
            }
        )
        result = classify_trend(df, ma20=97, ma50=100)
        assert result["trend"] == "SIDEWAYS"

    def test_strong_strength(self):
        df = pd.DataFrame({"close": [110], "open": [109]})
        result = classify_trend(df, ma20=100, ma50=95)
        assert result["strength"] == "strong"

    def test_moderate_strength(self):
        df = pd.DataFrame({"close": [103], "open": [102]})
        result = classify_trend(df, ma20=100, ma50=95)
        assert result["strength"] == "moderate"

    def test_weak_strength(self):
        df = pd.DataFrame({"close": [101], "open": [100]})
        result = classify_trend(df, ma20=100, ma50=95)
        assert result["strength"] == "weak"

    def test_bullish_momentum(self):
        df = pd.DataFrame(
            {
                "close": [101, 102, 103, 104, 105],
                "open": [100, 101, 102, 103, 104],
            }
        )
        result = classify_trend(df, ma20=103, ma50=100)
        assert result["momentum"] == "bullish"

    def test_bearish_momentum(self):
        df = pd.DataFrame(
            {
                "close": [99, 98, 97, 96, 95],
                "open": [100, 99, 98, 97, 96],
            }
        )
        result = classify_trend(df, ma20=97, ma50=100)
        assert result["momentum"] == "bearish"

    def test_neutral_momentum(self):
        df = pd.DataFrame(
            {
                "close": [101, 99, 100, 98, 99],
                "open": [100, 100, 99, 99, 98],
            }
        )
        result = classify_trend(df, ma20=99, ma50=100)
        assert result["momentum"] == "neutral"

    def test_handles_none_mas(self):
        df = pd.DataFrame({"close": [100], "open": [99]})
        result = classify_trend(df, ma20=None, ma50=None)
        assert result["trend"] == "UNKNOWN"


class TestGenerateAnalysisText:
    """Tests for natural language analysis generation."""

    def test_includes_ticker_and_trend(self):
        result = generate_analysis_text(
            ticker="TCB",
            price=35.0,
            trend={"trend": "UPTREND", "strength": "moderate", "momentum": "bullish"},
            pattern={"pattern": None, "signal": None},
            levels={"nearest_support": 33.0},
            rsi=45.0,
            macd_hist=0.1,
        )
        assert "TCB" in result
        assert "UPTREND" in result
        assert "moderate" in result

    def test_includes_pattern_when_present(self):
        result = generate_analysis_text(
            ticker="TCB",
            price=35.0,
            trend={"trend": "SIDEWAYS", "strength": "weak", "momentum": "neutral"},
            pattern={"pattern": "hammer", "signal": "bullish_reversal"},
            levels={},
            rsi=None,
            macd_hist=None,
        )
        assert "hammer" in result
        assert "bullish_reversal" in result

    def test_rsi_oversold_zone(self):
        result = generate_analysis_text(
            ticker="TCB",
            price=35.0,
            trend={"trend": "DOWNTREND", "strength": "moderate", "momentum": "bearish"},
            pattern={"pattern": None, "signal": None},
            levels={},
            rsi=25.0,
            macd_hist=None,
        )
        assert "RSI 25 OVERSOLD" in result

    def test_rsi_overbought_zone(self):
        result = generate_analysis_text(
            ticker="TCB",
            price=35.0,
            trend={"trend": "UPTREND", "strength": "strong", "momentum": "bullish"},
            pattern={"pattern": None, "signal": None},
            levels={},
            rsi=75.0,
            macd_hist=None,
        )
        assert "RSI 75 OVERBOUGHT" in result

    def test_rsi_approaching_oversold(self):
        result = generate_analysis_text(
            ticker="TCB",
            price=35.0,
            trend={"trend": "SIDEWAYS", "strength": "weak", "momentum": "neutral"},
            pattern={"pattern": None, "signal": None},
            levels={},
            rsi=35.0,
            macd_hist=None,
        )
        assert "approaching oversold" in result

    def test_includes_support_distance(self):
        result = generate_analysis_text(
            ticker="TCB",
            price=100.0,
            trend={"trend": "UPTREND", "strength": "moderate", "momentum": "bullish"},
            pattern={"pattern": None, "signal": None},
            levels={"nearest_support": 95.0},
            rsi=50.0,
            macd_hist=0.1,
        )
        assert "above support" in result
        assert "95" in result

    def test_macd_bullish_indicator(self):
        result = generate_analysis_text(
            ticker="TCB",
            price=35.0,
            trend={"trend": "UPTREND", "strength": "moderate", "momentum": "bullish"},
            pattern={"pattern": None, "signal": None},
            levels={},
            rsi=50.0,
            macd_hist=0.5,
        )
        assert "MACD bullish" in result

    def test_macd_bearish_indicator(self):
        result = generate_analysis_text(
            ticker="TCB",
            price=35.0,
            trend={"trend": "DOWNTREND", "strength": "moderate", "momentum": "bearish"},
            pattern={"pattern": None, "signal": None},
            levels={},
            rsi=50.0,
            macd_hist=-0.5,
        )
        assert "MACD bearish" in result

    def test_uses_20d_range_not_swing_range(self):
        """Should use 20d range in analysis text, not swing points."""
        result = generate_analysis_text(
            ticker="VHM",
            price=91.3,
            trend={"trend": "SIDEWAYS", "strength": "strong", "momentum": "neutral"},
            pattern={"pattern": "bearish_engulfing", "signal": "bearish_reversal"},
            levels={
                "swing_high": 127.5,
                "swing_low": 117.5,
                "range_20d_high": 150.9,
                "range_20d_low": 90.8,
                "nearest_support": 90.8,
            },
            rsi=30.0,
            macd_hist=-3.99,
        )
        assert "90.8" in result
        assert "150.9" in result
        assert "Range: 117.5-127.5" not in result
