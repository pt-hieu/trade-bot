"""Catalyst promotion tests for classify_strategy."""

from __future__ import annotations

from agents.tools.strategy_classifier import classify_strategy


def _mr_technicals() -> dict:
    """Technicals that deterministically classify as MEAN_REVERSION.

    RSI 42 + SIDEWAYS + 6% from support skips BOUNCE (needs RSI<40 + dist<=5%)
    and TREND (needs UPTREND) and lands on MEAN_REVERSION.
    """
    return {
        "close": 50_000,
        "rsi": 42.0,
        "volume_vs_avg": 0.9,
        "trend": {"trend": "SIDEWAYS"},
        "pattern": {},
        "levels": {"nearest_support": 47_000, "swing_low": 47_000},
    }


def test_mr_without_catalyst_stays_mr() -> None:
    result = classify_strategy(_mr_technicals(), has_positive_active_catalyst=False)
    assert result.strategy == "MEAN_REVERSION"


def test_mr_with_catalyst_promotes_to_momentum() -> None:
    result = classify_strategy(_mr_technicals(), has_positive_active_catalyst=True)
    assert result.strategy == "MOMENTUM"
    assert any("catalyst" in signal.lower() for signal in result.matched_signals)


def test_trend_not_affected_by_catalyst() -> None:
    tech = {
        "close": 50_000,
        "rsi": 55.0,
        "ma20": 49_500,
        "ma50": 48_000,
        "volume_vs_avg": 1.2,
        "trend": {"trend": "UPTREND"},
        "pattern": {},
        "levels": {"nearest_support": 48_000, "swing_low": 47_000},
    }
    with_catalyst = classify_strategy(tech, has_positive_active_catalyst=True)
    without = classify_strategy(tech, has_positive_active_catalyst=False)
    # Both should be TREND (promotion only fires on MEAN_REVERSION branch).
    assert with_catalyst.strategy == without.strategy == "TREND"
