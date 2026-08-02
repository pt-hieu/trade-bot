"""Strategy classifier: MEAN_REVERSION + PULLBACK."""

from agents.tools.strategy_classifier import classify_strategy
from tests.unit._fixtures.strategy_classifier import make_technicals


class TestMeanReversion:
    """RSI < 45 + within 8% of support + DOWNTREND or SIDEWAYS."""

    def test_downtrend_rsi_below_45_near_support_returns_mean_reversion(self):
        technicals = make_technicals(
            close=46_000, rsi=42.0, nearest_support=44_000, trend_direction="DOWNTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "MEAN_REVERSION"

    def test_sideways_trend_eligible_for_mean_reversion(self):
        technicals = make_technicals(
            close=46_000, rsi=41.0, nearest_support=44_000, trend_direction="SIDEWAYS"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "MEAN_REVERSION"

    def test_uptrend_not_eligible_for_mean_reversion(self):
        technicals = make_technicals(
            close=46_000,
            rsi=40.0,
            nearest_support=44_000,
            ma20=None,
            ma50=None,
            trend_direction="UPTREND",
        )
        result = classify_strategy(technicals)
        assert result.strategy != "MEAN_REVERSION"

    def test_rsi_exactly_45_no_mean_reversion(self):
        technicals = make_technicals(
            close=46_000, rsi=45.0, nearest_support=44_000, trend_direction="DOWNTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "MEAN_REVERSION"

    def test_rsi_44_99_returns_mean_reversion(self):
        technicals = make_technicals(
            close=46_000, rsi=44.99, nearest_support=44_000, trend_direction="DOWNTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "MEAN_REVERSION"

    def test_price_within_8pct_of_support_returns_mean_reversion(self):
        support = 44_000
        close = support * 1.08
        technicals = make_technicals(
            close=close, rsi=42.0, nearest_support=support, trend_direction="DOWNTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "MEAN_REVERSION"

    def test_price_beyond_8pct_no_mean_reversion(self):
        support = 44_000
        close = support * 1.081
        technicals = make_technicals(
            close=close, rsi=42.0, nearest_support=support, trend_direction="DOWNTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "MEAN_REVERSION"

    def test_mean_reversion_confidence_in_valid_range(self):
        technicals = make_technicals(
            close=46_000, rsi=42.0, nearest_support=44_000, trend_direction="DOWNTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "MEAN_REVERSION"
        assert 0.45 <= result.confidence <= 0.85

    def test_lower_rsi_closer_to_support_higher_confidence(self):
        technicals_strong = make_technicals(
            close=44_100, rsi=41.0, nearest_support=44_000, trend_direction="DOWNTREND"
        )
        technicals_weak = make_technicals(
            close=47_000, rsi=44.0, nearest_support=44_000, trend_direction="DOWNTREND"
        )
        result_strong = classify_strategy(technicals_strong)
        result_weak = classify_strategy(technicals_weak)
        assert result_strong.strategy == "MEAN_REVERSION"
        assert result_weak.strategy == "MEAN_REVERSION"
        assert result_strong.confidence > result_weak.confidence


class TestPullback:
    """Price between MA20 and MA50 (or near MA50) in UPTREND/SIDEWAYS."""

    def test_price_between_ma20_and_ma50_uptrend_returns_pullback(self):
        technicals = make_technicals(
            close=48_500,
            rsi=70.0,
            ma20=50_000,
            ma50=47_000,
            volume_vs_avg=0.9,
            trend_direction="UPTREND",
        )
        result = classify_strategy(technicals)
        assert result.strategy == "PULLBACK"
        assert result.confidence == 0.55

    def test_price_between_ma20_and_ma50_sideways_returns_pullback(self):
        technicals = make_technicals(
            close=48_500,
            rsi=70.0,
            ma20=50_000,
            ma50=47_000,
            volume_vs_avg=0.9,
            trend_direction="SIDEWAYS",
        )
        result = classify_strategy(technicals)
        assert result.strategy == "PULLBACK"

    def test_price_near_ma50_within_3pct_returns_pullback(self):
        ma50 = 48_000
        close = ma50 * 1.029
        technicals = make_technicals(
            close=close,
            rsi=70.0,
            ma20=55_000,
            ma50=ma50,
            volume_vs_avg=0.9,
            trend_direction="UPTREND",
        )
        result = classify_strategy(technicals)
        assert result.strategy == "PULLBACK"

    def test_price_near_ma50_exactly_3pct_returns_pullback(self):
        ma50 = 48_000
        close = ma50 * 1.03
        technicals = make_technicals(
            close=close,
            rsi=70.0,
            ma20=55_000,
            ma50=ma50,
            volume_vs_avg=0.9,
            trend_direction="UPTREND",
        )
        result = classify_strategy(technicals)
        assert result.strategy == "PULLBACK"

    def test_price_near_ma50_above_3pct_and_not_between_mas_no_pullback(self):
        ma50 = 48_000
        close = ma50 * 1.031
        ma20 = 45_000
        technicals = make_technicals(
            close=close, rsi=50.0, ma20=ma20, ma50=ma50, trend_direction="UPTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "PULLBACK"

    def test_downtrend_not_eligible_for_pullback(self):
        technicals = make_technicals(
            close=48_500, rsi=50.0, ma20=50_000, ma50=47_000, trend_direction="DOWNTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "PULLBACK"

    def test_missing_ma20_no_pullback(self):
        technicals = make_technicals(
            close=48_500, rsi=50.0, ma20=None, ma50=47_000, trend_direction="UPTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "PULLBACK"

    def test_missing_ma50_no_pullback(self):
        technicals = make_technicals(
            close=48_500, rsi=50.0, ma20=50_000, ma50=None, trend_direction="UPTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "PULLBACK"
