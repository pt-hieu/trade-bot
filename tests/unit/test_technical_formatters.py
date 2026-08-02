"""Unit tests for technicals prose formatter."""

from agents.tools.technicals import _format_technicals_prose


def _base_data(**overrides) -> dict:
    """Minimal technicals dict."""
    data = {
        "ticker": "TCB",
        "close": 35900,
        "rsi": None,
        "trend": {"trend": "UPTREND", "strength": "moderate", "momentum": "bullish"},
        "pattern": {"pattern": None, "signal": None},
        "levels": {},
        "volume_context": {},
        "macd_histogram": None,
    }
    data.update(overrides)
    return data


class TestFormatTechnicalsProse:
    def test_basic_structure(self):
        result = _format_technicals_prose(_base_data())
        assert "TCB Technical Analysis:" in result
        assert "UPTREND" in result

    def test_error_passthrough(self):
        result = _format_technicals_prose({"error": "No data"})
        assert "No data" in result

    def test_rsi_oversold(self):
        result = _format_technicals_prose(_base_data(rsi=25))
        assert "OVERSOLD" in result
        assert "buy zone" not in result  # Removed biased label

    def test_rsi_overbought(self):
        result = _format_technicals_prose(_base_data(rsi=75))
        assert "OVERBOUGHT" in result

    def test_rsi_neutral(self):
        result = _format_technicals_prose(_base_data(rsi=45))
        assert "neutral zone" in result

    def test_rsi_approaching_oversold(self):
        result = _format_technicals_prose(_base_data(rsi=35))
        assert "approaching oversold" in result

    def test_macd_bullish(self):
        result = _format_technicals_prose(_base_data(macd_histogram=150))
        assert "bullish" in result

    def test_macd_bearish(self):
        result = _format_technicals_prose(_base_data(macd_histogram=-200))
        assert "bearish" in result

    def test_pattern_detected(self):
        data = _base_data(pattern={"pattern": "hammer", "signal": "bullish_reversal"})
        result = _format_technicals_prose(data)
        assert "hammer" in result
        assert "bullish_reversal" in result

    def test_volume_bounce_confirmed(self):
        data = _base_data(volume_context={"volume_trend": "increasing", "bounce_confirmed": True})
        result = _format_technicals_prose(data)
        assert "CONFIRMED" in result

    def test_support_distance(self):
        data = _base_data(
            close=36000,
            levels={
                "nearest_support": 34000,
                "nearest_resistance": 38000,
                "range_20d_low": 33000,
                "range_20d_high": 39000,
            },
        )
        result = _format_technicals_prose(data)
        assert "above support" in result
        assert "Range:" in result
