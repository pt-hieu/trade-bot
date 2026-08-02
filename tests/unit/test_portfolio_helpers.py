"""
Unit tests for scripts/agents/tools/portfolio.py helper functions.

Tests pure functions that don't require database access.
"""

import pytest

from agents.tools.portfolio_learnings import (
    _normalize_bias,
)


class TestNormalizeBias:
    """Tests for _normalize_bias function."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Bullish mappings
            ("Strong/Resilient", "bullish"),
            ("strong", "bullish"),
            ("Resilient market", "bullish"),
            ("bullish", "bullish"),
            ("Bullish sentiment", "bullish"),
            ("hot sector", "bullish"),
            ("opportunity here", "bullish"),
            # Bearish mappings
            ("Weak/Choppy", "bearish"),
            ("weak", "bearish"),
            ("Choppy market", "bearish"),
            ("bearish", "bearish"),
            ("cold sector", "bearish"),
            ("downtrend", "bearish"),
            # Neutral mappings
            ("Mixed", "neutral"),
            ("mixed signals", "neutral"),
            ("unknown", "neutral"),
            ("something else", "neutral"),
        ],
    )
    def test_normalize(self, raw, expected):
        assert _normalize_bias(raw) == expected


class TestSectorBiasHelper:
    """Tests for _get_sector_bias internal helper."""

    def test_classifies_hot_and_cold(self, sample_learnings):
        """Should classify sectors as hot or cold."""
        from agents.tools.portfolio_learnings import _get_sector_bias

        insights = sample_learnings.get("sector_insights", [])
        result = _get_sector_bias(insights, None)

        assert result["query"] == "sector_bias"
        assert "banking" in result["hot"]  # Strong/Resilient -> bullish -> hot
        assert "real_estate" in result["cold"]  # Weak/Choppy -> bearish -> cold

    def test_filters_by_sector(self, sample_learnings):
        """Should filter to specific sector."""
        from agents.tools.portfolio_learnings import _get_sector_bias

        insights = sample_learnings.get("sector_insights", [])
        result = _get_sector_bias(insights, "banking")

        assert len(result["data"]) == 1
        assert result["data"][0]["sector"] == "banking"


class TestTickerAccuracyHelper:
    """Tests for _get_ticker_accuracy internal helper."""

    def test_classifies_high_and_low_accuracy(self, sample_learnings):
        """Should classify tickers by accuracy."""
        from agents.tools.portfolio_learnings import _get_ticker_accuracy

        insights = sample_learnings.get("ticker_insights", [])
        result = _get_ticker_accuracy(insights, None)

        assert result["query"] == "ticker_accuracy"
        assert "TCB" in result["high"]  # 75% accuracy
        assert "FPT" in result["high"]  # 80% accuracy
        assert "VHM" in result["low"]  # 25% accuracy

    def test_filters_by_ticker(self, sample_learnings):
        """Should filter to specific ticker."""
        from agents.tools.portfolio_learnings import _get_ticker_accuracy

        insights = sample_learnings.get("ticker_insights", [])
        result = _get_ticker_accuracy(insights, "TCB")

        assert len(result["data"]) == 1
        assert result["data"][0]["ticker"] == "TCB"


# TestRotationPatternsHelper and TestMacroPatternsHelper removed:
# sync helper functions _get_rotation_patterns and _get_macro_patterns
# were removed in favor of async DB queries in get_learnings_async()
