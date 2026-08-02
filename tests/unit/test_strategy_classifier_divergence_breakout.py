"""Strategy classifier: DIVERGENCE + BREAKOUT + priority ordering + UNCLASSIFIED + confidence range."""

import pytest

from agents.tools.strategy_classifier import (
    StrategyClassification,
    _divergence_confidence,
    classify_strategy,
)
from tests.unit._fixtures.strategy_classifier import make_technicals


class TestDivergence:
    """price <= swing_low AND current RSI > RSI at swing_low_date."""

    def test_price_at_swing_low_rsi_higher_returns_divergence(self):
        technicals = make_technicals(close=45_000, rsi=35.0, swing_low=45_000)
        result = classify_strategy(technicals, rsi_at_swing_low=25.0)
        assert result.strategy == "DIVERGENCE"
        assert result.confidence > 0
        assert len(result.matched_signals) == 2

    def test_price_below_swing_low_rsi_higher_returns_divergence(self):
        technicals = make_technicals(close=44_000, rsi=38.0, swing_low=45_000)
        result = classify_strategy(technicals, rsi_at_swing_low=28.0)
        assert result.strategy == "DIVERGENCE"

    def test_price_above_swing_low_no_divergence(self):
        technicals = make_technicals(
            close=46_000, rsi=35.0, swing_low=45_000, trend_direction="DOWNTREND"
        )
        result = classify_strategy(technicals, rsi_at_swing_low=25.0)
        assert result.strategy != "DIVERGENCE"

    def test_rsi_lower_than_at_swing_low_no_divergence(self):
        technicals = make_technicals(close=44_000, rsi=20.0, swing_low=45_000)
        result = classify_strategy(technicals, rsi_at_swing_low=25.0)
        assert result.strategy != "DIVERGENCE"

    def test_rsi_equal_to_swing_low_rsi_no_divergence(self):
        technicals = make_technicals(close=44_000, rsi=25.0, swing_low=45_000)
        result = classify_strategy(technicals, rsi_at_swing_low=25.0)
        assert result.strategy != "DIVERGENCE"

    def test_no_rsi_at_swing_low_skips_divergence(self):
        technicals = make_technicals(close=44_000, rsi=35.0, swing_low=45_000)
        result = classify_strategy(technicals, rsi_at_swing_low=None)
        assert result.strategy != "DIVERGENCE"

    def test_divergence_takes_priority_over_bounce(self):
        technicals = make_technicals(
            close=44_500,
            rsi=38.0,
            swing_low=45_000,
            nearest_support=44_000,
        )
        result = classify_strategy(technicals, rsi_at_swing_low=28.0)
        assert result.strategy == "DIVERGENCE"

    @pytest.mark.parametrize(
        "rsi_diff,expected_confidence",
        [
            (11.0, 0.9),
            (10.1, 0.9),
            (7.0, 0.75),
            (5.1, 0.75),
            (3.0, 0.6),
            (0.1, 0.6),
        ],
    )
    def test_divergence_confidence_tiers(self, rsi_diff, expected_confidence):
        confidence = _divergence_confidence(rsi_now=30.0 + rsi_diff, rsi_at_low=30.0)
        assert confidence == expected_confidence


class TestBreakout:
    """close > nearest_resistance AND volume >= 1.5x avg."""

    def test_above_resistance_high_volume_returns_breakout(self):
        technicals = make_technicals(close=56_000, nearest_resistance=55_000, volume_vs_avg=1.8)
        result = classify_strategy(technicals)
        assert result.strategy == "BREAKOUT"

    def test_volume_exactly_1_5x_returns_breakout(self):
        technicals = make_technicals(close=56_000, nearest_resistance=55_000, volume_vs_avg=1.5)
        result = classify_strategy(technicals)
        assert result.strategy == "BREAKOUT"

    def test_volume_below_1_5x_no_breakout(self):
        technicals = make_technicals(close=56_000, nearest_resistance=55_000, volume_vs_avg=1.49)
        result = classify_strategy(technicals)
        assert result.strategy != "BREAKOUT"

    def test_price_at_resistance_no_breakout(self):
        technicals = make_technicals(close=55_000, nearest_resistance=55_000, volume_vs_avg=2.0)
        result = classify_strategy(technicals)
        assert result.strategy != "BREAKOUT"

    def test_price_below_resistance_no_breakout(self):
        technicals = make_technicals(close=54_000, nearest_resistance=55_000, volume_vs_avg=2.0)
        result = classify_strategy(technicals)
        assert result.strategy != "BREAKOUT"

    def test_breakout_confidence_increases_with_volume(self):
        technicals_low_vol = make_technicals(
            close=56_000, nearest_resistance=55_000, volume_vs_avg=1.5
        )
        technicals_high_vol = make_technicals(
            close=56_000, nearest_resistance=55_000, volume_vs_avg=3.0
        )
        result_low = classify_strategy(technicals_low_vol)
        result_high = classify_strategy(technicals_high_vol)
        assert result_high.confidence > result_low.confidence

    def test_breakout_confidence_capped_at_1(self):
        technicals = make_technicals(close=56_000, nearest_resistance=55_000, volume_vs_avg=10.0)
        result = classify_strategy(technicals)
        assert result.confidence <= 1.0

    def test_breakout_takes_priority_over_bounce(self):
        technicals = make_technicals(
            close=56_000,
            rsi=38.0,
            nearest_resistance=55_000,
            nearest_support=55_000,
            volume_vs_avg=1.6,
        )
        result = classify_strategy(technicals)
        assert result.strategy == "BREAKOUT"


class TestPriorityOrdering:
    """Verify the documented priority chain."""

    def test_divergence_beats_bounce(self):
        technicals = make_technicals(
            close=44_500,
            rsi=38.0,
            swing_low=45_000,
            nearest_support=44_000,
        )
        result = classify_strategy(technicals, rsi_at_swing_low=28.0)
        assert result.strategy == "DIVERGENCE"

    def test_breakout_beats_trend(self):
        technicals = make_technicals(
            close=56_000,
            rsi=58.0,
            ma20=55_500,
            nearest_resistance=55_000,
            volume_vs_avg=1.6,
            trend_direction="UPTREND",
        )
        result = classify_strategy(technicals)
        assert result.strategy == "BREAKOUT"

    def test_bounce_beats_trend(self):
        technicals = make_technicals(
            close=49_000,
            rsi=38.0,
            ma20=49_500,
            nearest_support=48_000,
            trend_direction="UPTREND",
        )
        result = classify_strategy(technicals)
        assert result.strategy == "BOUNCE"

    def test_trend_beats_mean_reversion(self):
        technicals = make_technicals(
            close=49_000,
            rsi=40.0,
            ma20=49_500,
            nearest_support=48_000,
            trend_direction="UPTREND",
        )
        result = classify_strategy(technicals)
        assert result.strategy == "TREND"

    def test_momentum_beats_pullback(self):
        technicals = make_technicals(
            close=49_000,
            rsi=68.0,
            ma20=48_000,
            ma50=55_000,
            volume_vs_avg=1.3,
            trend_direction="SIDEWAYS",
        )
        result = classify_strategy(technicals)
        assert result.strategy == "MOMENTUM"


class TestUnclassified:
    """Fallthrough when no strategy matches."""

    def test_missing_all_data_returns_unclassified(self):
        technicals = make_technicals(
            rsi=None,
            ma20=None,
            ma50=None,
            volume_vs_avg=None,
            nearest_support=None,
            nearest_resistance=None,
            swing_low=None,
        )
        result = classify_strategy(technicals)
        assert result.strategy == "UNCLASSIFIED"
        assert result.confidence == 0.0
        assert result.matched_signals == []

    def test_sideways_rsi_in_middle_no_ma_proximity_returns_unclassified(self):
        technicals = make_technicals(
            close=50_000,
            rsi=50.0,
            ma20=None,
            ma50=None,
            volume_vs_avg=0.8,
            nearest_support=None,
            nearest_resistance=55_000,
            swing_low=None,
            trend_direction="SIDEWAYS",
        )
        result = classify_strategy(technicals)
        assert result.strategy == "UNCLASSIFIED"

    def test_zero_close_returns_unclassified(self):
        technicals = make_technicals(close=0)
        result = classify_strategy(technicals)
        assert result.strategy == "UNCLASSIFIED"

    def test_returns_strategy_classification_dataclass(self):
        technicals = make_technicals(
            rsi=None,
            ma20=None,
            ma50=None,
            volume_vs_avg=None,
            nearest_support=None,
            nearest_resistance=None,
            swing_low=None,
        )
        result = classify_strategy(technicals)
        assert isinstance(result, StrategyClassification)
        assert isinstance(result.strategy, str)
        assert isinstance(result.confidence, float)
        assert isinstance(result.matched_signals, list)


class TestConfidenceScoring:
    """Verify confidence values are within [0, 1] for all strategies."""

    @pytest.mark.parametrize(
        "strategy_name,technicals_kwargs,rsi_at_swing_low",
        [
            (
                "DIVERGENCE",
                {"close": 44_000, "rsi": 38.0, "swing_low": 45_000},
                28.0,
            ),
            (
                "BREAKOUT",
                {"close": 56_000, "nearest_resistance": 55_000, "volume_vs_avg": 1.8},
                None,
            ),
            (
                "BOUNCE",
                {"close": 46_000, "rsi": 30.0, "nearest_support": 44_000},
                None,
            ),
            (
                "TREND",
                {"close": 50_000, "rsi": 55.0, "ma20": 49_000, "trend_direction": "UPTREND"},
                None,
            ),
            (
                "MEAN_REVERSION",
                {
                    "close": 46_000,
                    "rsi": 42.0,
                    "nearest_support": 44_000,
                    "trend_direction": "DOWNTREND",
                },
                None,
            ),
            (
                "MOMENTUM",
                {
                    "close": 52_000,
                    "rsi": 68.0,
                    "ma20": 50_000,
                    "volume_vs_avg": 1.5,
                    "trend_direction": "SIDEWAYS",
                },
                None,
            ),
        ],
    )
    def test_confidence_in_0_to_1_range(self, strategy_name, technicals_kwargs, rsi_at_swing_low):
        technicals = make_technicals(**technicals_kwargs)
        result = classify_strategy(technicals, rsi_at_swing_low=rsi_at_swing_low)
        assert result.strategy == strategy_name, f"Expected {strategy_name}, got {result.strategy}"
        assert 0.0 <= result.confidence <= 1.0, (
            f"{strategy_name} confidence={result.confidence} out of range"
        )
