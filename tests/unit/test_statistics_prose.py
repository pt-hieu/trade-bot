"""SWI-125 Surface 5a: nested-dict unpack in statistics prose formatters.

The May 12 pipeline-review surfaced `statistic.get_stats` returning
`{"error": "unsupported operand type(s) for *: 'dict' and 'int'"}` because
the formatter assumed `by_rsi_zone` was `dict[str, float]` while the API
returns `dict[str, {"count": int, "reversal_rate": float}]`. Same shape
mismatch on `with_high_volume`. Latent since b1bf33ff (str/dict split).
The sibling `_format_streak_prose` rendered raw integer counts as
percentages (e.g. '300%' for 3 occurrences); fixed alongside.
"""

from __future__ import annotations

from agents.tools.statistics import _format_price_action_prose, _format_streak_prose


def test_price_action_prose_with_nested_by_rsi_zone() -> None:
    data = {
        "reversal_rate": 0.42,
        "with_high_volume": {"count": 15, "reversal_rate": 0.55},
        "by_rsi_zone": {
            "oversold_0_30": {"count": 5, "reversal_rate": 0.60},
            "neutral_30_50": {"count": 8, "reversal_rate": 0.40},
            "overbought_50_plus": {"count": 12, "reversal_rate": 0.25},
        },
    }
    prose = _format_price_action_prose(data, days_back=90)
    assert "42%" in prose  # top-level reversal_rate * 100
    assert "55%" in prose  # high-vol nested reversal_rate
    assert "60% reversal" in prose
    assert "25% reversal" in prose


def test_price_action_prose_missing_high_volume() -> None:
    data = {
        "reversal_rate": 0.3,
        "with_high_volume": {"count": 0, "reversal_rate": 0.0},
        "by_rsi_zone": {},
    }
    prose = _format_price_action_prose(data, days_back=30)
    assert "30%" in prose
    # high-vol with rate=0 should NOT emit the high-vol clause
    assert "high volume" not in prose


def test_price_action_prose_error_passthrough() -> None:
    prose = _format_price_action_prose({"error": "no data"}, days_back=90)
    assert "no data" in prose


def test_streak_prose_distribution_as_relative_frequency() -> None:
    # 6 streaks total: lengths 1×3, 2×2, 3×1 → percentages 50%, 33%, 17%.
    data = {
        "max_consecutive": 3,
        "avg_consecutive": 1.67,
        "current_streak": 0,
        "distribution": {1: 3, 2: 2, 3: 1},
    }
    prose = _format_streak_prose(data, ticker="FPT", condition="rsi_below_30", days_back=90)
    assert "1 day (50%)" in prose
    assert "2 days (33%)" in prose
    assert "3 days (17%)" in prose
    assert "Max consecutive days: 3" in prose


def test_streak_prose_singular_plural() -> None:
    data = {
        "max_consecutive": 1,
        "avg_consecutive": 1.0,
        "current_streak": 1,
        "distribution": {1: 5},
    }
    prose = _format_streak_prose(data, ticker="VNM", condition="closed_at_low", days_back=60)
    assert "Distribution: 1 day (100%)" in prose


def test_streak_prose_empty_distribution() -> None:
    data = {
        "max_consecutive": 0,
        "avg_consecutive": 0,
        "current_streak": 0,
        "distribution": {},
    }
    prose = _format_streak_prose(data, ticker="X", condition="rsi_below_30", days_back=90)
    assert "Distribution" not in prose
