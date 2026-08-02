"""Unit tests for technicals helper functions."""

from data.technicals import find_nearest_levels, generate_analysis_text

# ── find_nearest_levels ───────────────────────────────────────────────────


class TestFindNearestLevels:
    def test_support_below_price(self):
        result = find_nearest_levels(
            price=100,
            ma20=90,
            ma50=None,
            swing_high=None,
            swing_low=None,
            range_high=None,
            range_low=None,
        )
        assert result["nearest_support"] == 90

    def test_resistance_above_price(self):
        result = find_nearest_levels(
            price=100,
            ma20=None,
            ma50=None,
            swing_high=110,
            swing_low=None,
            range_high=None,
            range_low=None,
        )
        assert result["nearest_resistance"] == 110

    def test_closest_among_many(self):
        """Should pick the support closest to (but below) price."""
        result = find_nearest_levels(
            price=100,
            ma20=95,
            ma50=85,
            swing_high=None,
            swing_low=80,
            range_high=None,
            range_low=75,
        )
        assert result["nearest_support"] == 95  # max of supports below price

    def test_closest_resistance(self):
        """Should pick the resistance closest to (but above) price."""
        result = find_nearest_levels(
            price=100,
            ma20=105,
            ma50=120,
            swing_high=115,
            swing_low=None,
            range_high=110,
            range_low=None,
        )
        assert result["nearest_resistance"] == 105  # min of resistances above

    def test_all_none(self):
        result = find_nearest_levels(
            price=100,
            ma20=None,
            ma50=None,
            swing_high=None,
            swing_low=None,
            range_high=None,
            range_low=None,
        )
        assert result == {}

    def test_level_at_price_excluded(self):
        """Level exactly at price is neither support nor resistance."""
        result = find_nearest_levels(
            price=100,
            ma20=100,
            ma50=None,
            swing_high=None,
            swing_low=None,
            range_high=None,
            range_low=None,
        )
        assert "nearest_support" not in result
        assert "nearest_resistance" not in result

    def test_both_support_and_resistance(self):
        result = find_nearest_levels(
            price=100,
            ma20=95,
            ma50=110,
            swing_high=None,
            swing_low=85,
            range_high=None,
            range_low=None,
        )
        assert result["nearest_support"] == 95
        assert result["nearest_resistance"] == 110

    # ── SWI-3a: MA-free swing target / swing low ──────────────────────────

    def test_swing_target_ma_free_prefers_higher(self):
        """nearest_swing_target ignores MAs and picks the HIGHER of swing_high vs range_high."""
        result = find_nearest_levels(
            price=100,
            ma20=101,
            ma50=None,
            swing_high=110,
            swing_low=None,
            range_high=115,
            range_low=None,
        )
        # nearest_resistance unchanged (MA-inclusive, picks closest above)
        assert result["nearest_resistance"] == 101
        # nearest_swing_target is MA-free, prefers max of swing_high vs range_high
        assert result["nearest_swing_target"] == 115

    def test_swing_target_absent_when_no_swings(self):
        """No swing target emitted when only MAs are above price."""
        result = find_nearest_levels(
            price=100,
            ma20=101,
            ma50=120,
            swing_high=None,
            swing_low=None,
            range_high=None,
            range_low=None,
        )
        assert result["nearest_resistance"] == 101
        assert "nearest_swing_target" not in result

    def test_swing_low_ma_free(self):
        """nearest_swing_low ignores MAs and picks the closest swing/range low below."""
        result = find_nearest_levels(
            price=100,
            ma20=98,  # MA between price and swing_low; should NOT influence swing_low
            ma50=None,
            swing_high=None,
            swing_low=92,
            range_high=None,
            range_low=88,
        )
        # nearest_support is MA-inclusive (picks 98)
        assert result["nearest_support"] == 98
        # nearest_swing_low is MA-free (picks max of swing/range lows below = 92)
        assert result["nearest_swing_low"] == 92

    def test_swing_low_absent_when_no_swings(self):
        result = find_nearest_levels(
            price=100,
            ma20=95,
            ma50=None,
            swing_high=None,
            swing_low=None,
            range_high=None,
            range_low=None,
        )
        assert result["nearest_support"] == 95
        assert "nearest_swing_low" not in result


# ── generate_analysis_text ────────────────────────────────────────────────


class TestGenerateAnalysisText:
    def test_uptrend_with_indicators(self):
        trend = {"trend": "UPTREND", "strength": "strong", "momentum": "bullish"}
        pattern = {"pattern": None, "signal": None}
        levels = {"nearest_support": 95}
        text = generate_analysis_text("FPT", 100, trend, pattern, levels, rsi=45, macd_hist=150)
        assert "FPT: UPTREND (strong)" in text
        assert "RSI 45" in text
        assert "MACD bullish" in text

    def test_oversold_rsi(self):
        trend = {"trend": "DOWNTREND", "strength": "weak", "momentum": "bearish"}
        text = generate_analysis_text("TCB", 35, trend, {}, {}, rsi=25, macd_hist=None)
        assert "OVERSOLD" in text

    def test_pattern_in_text(self):
        trend = {"trend": "SIDEWAYS", "strength": "moderate", "momentum": "neutral"}
        pattern = {"pattern": "hammer", "signal": "bullish_reversal"}
        text = generate_analysis_text("VHM", 115, trend, pattern, {}, rsi=None, macd_hist=None)
        assert "hammer" in text
        assert "bullish_reversal" in text

    def test_range_context(self):
        trend = {"trend": "UPTREND", "strength": "moderate", "momentum": "neutral"}
        levels = {"range_20d_low": 90, "range_20d_high": 110}
        text = generate_analysis_text("NLG", 100, trend, {}, levels, rsi=None, macd_hist=None)
        assert "90-110" in text
