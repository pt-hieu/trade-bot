"""Strategy classifier: BOUNCE + TREND + MOMENTUM."""

import pytest

from agents.tools.strategy_classifier import _bounce_confidence, classify_strategy
from tests.unit._fixtures.strategy_classifier import make_technicals


class TestBounce:
    """RSI < 40 AND price within 5% of support (nearest_support preferred over swing_low)."""

    def test_oversold_near_support_returns_bounce(self):
        technicals = make_technicals(
            close=46_500, rsi=32.0, nearest_support=46_000, swing_low=44_000
        )
        result = classify_strategy(technicals)
        assert result.strategy == "BOUNCE"

    def test_uses_nearest_support_over_swing_low(self):
        technicals = make_technicals(
            close=46_500, rsi=35.0, nearest_support=46_000, swing_low=40_000
        )
        result = classify_strategy(technicals)
        assert result.strategy == "BOUNCE"

    def test_falls_back_to_swing_low_when_no_nearest_support(self):
        technicals = make_technicals(close=44_500, rsi=35.0, nearest_support=None, swing_low=44_000)
        result = classify_strategy(technicals)
        assert result.strategy == "BOUNCE"

    def test_rsi_exactly_40_no_bounce(self):
        technicals = make_technicals(close=46_500, rsi=40.0, nearest_support=46_000)
        result = classify_strategy(technicals)
        assert result.strategy != "BOUNCE"

    def test_rsi_39_99_within_threshold_returns_bounce(self):
        technicals = make_technicals(close=46_500, rsi=39.99, nearest_support=46_000)
        result = classify_strategy(technicals)
        assert result.strategy == "BOUNCE"

    def test_price_exactly_5pct_from_support_returns_bounce(self):
        support = 46_000
        close = support * 1.05
        technicals = make_technicals(close=close, rsi=35.0, nearest_support=support)
        result = classify_strategy(technicals)
        assert result.strategy == "BOUNCE"

    def test_price_beyond_5pct_from_support_no_bounce(self):
        support = 46_000
        close = support * 1.051
        technicals = make_technicals(close=close, rsi=35.0, nearest_support=support)
        result = classify_strategy(technicals)
        assert result.strategy != "BOUNCE"

    @pytest.mark.parametrize(
        "rsi,dist_pct,expected_min_confidence",
        [
            (20.0, 0.5, 0.75),
            (35.0, 2.5, 0.55),
            (39.0, 4.9, 0.55),
        ],
    )
    def test_bounce_confidence_range(self, rsi, dist_pct, expected_min_confidence):
        support = 46_000
        close = support * (1 + dist_pct / 100)
        technicals = make_technicals(close=close, rsi=rsi, nearest_support=support)
        result = classify_strategy(technicals)
        if result.strategy == "BOUNCE":
            assert result.confidence >= expected_min_confidence

    def test_bounce_confidence_helper_lower_rsi_higher_confidence(self):
        confidence_deep = _bounce_confidence(rsi=10.0, dist_pct=0.0)
        confidence_mild = _bounce_confidence(rsi=39.0, dist_pct=4.9)
        assert confidence_deep > confidence_mild

    def test_bounce_confidence_capped_at_1(self):
        confidence = _bounce_confidence(rsi=0.0, dist_pct=0.0)
        assert confidence <= 1.0


class TestTrend:
    """UPTREND + price within 5% of MA20 or MA50 + RSI 35-65."""

    def test_uptrend_near_ma20_rsi_in_range_returns_trend(self):
        technicals = make_technicals(
            close=50_000, rsi=55.0, ma20=49_000, ma50=47_000, trend_direction="UPTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "TREND"
        assert result.confidence == 0.7

    def test_uptrend_near_ma50_rsi_in_range_returns_trend(self):
        technicals = make_technicals(
            close=50_000, rsi=55.0, ma20=40_000, ma50=48_500, trend_direction="UPTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "TREND"

    @pytest.mark.parametrize("rsi", [35.0, 50.0, 65.0])
    def test_rsi_boundary_values_return_trend(self, rsi):
        technicals = make_technicals(close=50_000, rsi=rsi, ma20=49_000, trend_direction="UPTREND")
        result = classify_strategy(technicals)
        assert result.strategy == "TREND"

    def test_rsi_below_35_no_trend(self):
        technicals = make_technicals(close=50_000, rsi=34.9, ma20=49_000, trend_direction="UPTREND")
        result = classify_strategy(technicals)
        assert result.strategy != "TREND"

    def test_rsi_above_65_no_trend(self):
        technicals = make_technicals(close=50_000, rsi=65.1, ma20=49_000, trend_direction="UPTREND")
        result = classify_strategy(technicals)
        assert result.strategy != "TREND"

    def test_sideways_not_eligible_for_trend(self):
        technicals = make_technicals(
            close=50_000, rsi=55.0, ma20=49_000, trend_direction="SIDEWAYS"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "TREND"

    def test_downtrend_not_eligible_for_trend(self):
        technicals = make_technicals(
            close=50_000, rsi=55.0, ma20=49_000, trend_direction="DOWNTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "TREND"

    def test_price_outside_5pct_of_both_mas_no_trend(self):
        technicals = make_technicals(
            close=50_000, rsi=55.0, ma20=44_000, ma50=43_000, trend_direction="UPTREND"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "TREND"


class TestMomentum:
    """RSI > 55 + price above MA20 + volume > 1.0x avg."""

    def test_strong_rsi_above_ma20_above_avg_volume_returns_momentum(self):
        technicals = make_technicals(
            close=52_000, rsi=68.0, ma20=50_000, volume_vs_avg=1.5, trend_direction="SIDEWAYS"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "MOMENTUM"

    def test_rsi_exactly_55_no_momentum(self):
        technicals = make_technicals(
            close=52_000, rsi=55.0, ma20=50_000, volume_vs_avg=1.5, trend_direction="SIDEWAYS"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "MOMENTUM"

    def test_rsi_55_01_above_ma20_returns_momentum(self):
        technicals = make_technicals(
            close=52_000, rsi=55.01, ma20=50_000, volume_vs_avg=1.1, trend_direction="SIDEWAYS"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "MOMENTUM"

    def test_price_below_ma20_no_momentum(self):
        technicals = make_technicals(
            close=48_000, rsi=60.0, ma20=50_000, volume_vs_avg=1.5, trend_direction="SIDEWAYS"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "MOMENTUM"

    def test_volume_exactly_1x_no_momentum(self):
        technicals = make_technicals(
            close=52_000, rsi=60.0, ma20=50_000, volume_vs_avg=1.0, trend_direction="SIDEWAYS"
        )
        result = classify_strategy(technicals)
        assert result.strategy != "MOMENTUM"

    def test_volume_1_01x_returns_momentum(self):
        technicals = make_technicals(
            close=52_000, rsi=60.0, ma20=50_000, volume_vs_avg=1.01, trend_direction="SIDEWAYS"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "MOMENTUM"

    def test_momentum_confidence_in_valid_range(self):
        technicals = make_technicals(
            close=52_000, rsi=65.0, ma20=50_000, volume_vs_avg=1.5, trend_direction="SIDEWAYS"
        )
        result = classify_strategy(technicals)
        assert result.strategy == "MOMENTUM"
        assert 0.5 <= result.confidence <= 0.85

    def test_higher_rsi_higher_volume_higher_confidence(self):
        technicals_strong = make_technicals(
            close=52_000, rsi=80.0, ma20=50_000, volume_vs_avg=2.5, trend_direction="SIDEWAYS"
        )
        technicals_weak = make_technicals(
            close=52_000, rsi=56.0, ma20=50_000, volume_vs_avg=1.05, trend_direction="SIDEWAYS"
        )
        result_strong = classify_strategy(technicals_strong)
        result_weak = classify_strategy(technicals_weak)
        assert result_strong.strategy == "MOMENTUM"
        assert result_weak.strategy == "MOMENTUM"
        assert result_strong.confidence > result_weak.confidence
