"""Belief calibration: base rate constants, dynamic computation, agent prediction
distribution, outcome reinforcement formatting."""

import pytest

from agents.belief_aggregation import FALLBACK_BASE_RATES
from agents.belief_models import (
    BASE_RATE_BEAR,
    BASE_RATE_BULL,
    BASE_RATE_NEUTRAL,
)


class TestBaseRateConstants:
    """Verify base rate constants reflect empirical Vietnamese market data."""

    def test_base_rates_sum_to_one(self):
        total = BASE_RATE_BULL + BASE_RATE_NEUTRAL + BASE_RATE_BEAR
        assert abs(total - 1.0) < 0.001

    def test_neutral_is_dominant(self):
        """NEUTRAL should be the largest base rate (empirically ~68%)."""
        assert BASE_RATE_NEUTRAL > BASE_RATE_BULL
        assert BASE_RATE_NEUTRAL > BASE_RATE_BEAR
        assert BASE_RATE_NEUTRAL >= 0.60  # Must reflect reality

    def test_bearish_is_rare(self):
        """BEARISH should be the smallest (empirically ~8%)."""
        assert BASE_RATE_BEAR < BASE_RATE_BULL
        assert BASE_RATE_BEAR <= 0.15

    def test_bullish_is_moderate(self):
        """BULLISH around 24%."""
        assert 0.15 <= BASE_RATE_BULL <= 0.35

    def test_fallback_base_rates_match_constants(self):
        assert FALLBACK_BASE_RATES["BULLISH"] == BASE_RATE_BULL
        assert FALLBACK_BASE_RATES["NEUTRAL"] == BASE_RATE_NEUTRAL
        assert FALLBACK_BASE_RATES["BEARISH"] == BASE_RATE_BEAR


class TestComputeEmpiricalBaseRates:
    """Test compute_empirical_base_rates from belief_queries.py."""

    @pytest.mark.asyncio
    async def test_raises_on_no_data(self):
        """Must raise ValueError when no scored beliefs exist."""
        from unittest.mock import AsyncMock, patch

        mock_db = AsyncMock()
        mock_db.fetch_all = AsyncMock(return_value=[])

        with patch("shared.neon.belief_queries.get_db", return_value=mock_db):
            from shared.neon.belief_queries import compute_empirical_base_rates

            with pytest.raises(ValueError, match="No scored beliefs found"):
                await compute_empirical_base_rates(days_back=90)

    @pytest.mark.asyncio
    async def test_computes_correct_distribution(self):
        """Given known counts, returns correct proportions."""
        from unittest.mock import AsyncMock, patch

        mock_rows = [
            {"actual_direction": "NEUTRAL", "cnt": 68},
            {"actual_direction": "BULLISH", "cnt": 24},
            {"actual_direction": "BEARISH", "cnt": 8},
        ]
        mock_db = AsyncMock()
        mock_db.fetch_all = AsyncMock(return_value=mock_rows)

        with patch("shared.neon.belief_queries.get_db", return_value=mock_db):
            from shared.neon.belief_queries import compute_empirical_base_rates

            rates = await compute_empirical_base_rates(days_back=90)

        assert abs(rates["BULLISH"] - 0.24) < 0.001
        assert abs(rates["NEUTRAL"] - 0.68) < 0.001
        assert abs(rates["BEARISH"] - 0.08) < 0.001
        # Must sum to 1.0
        assert abs(sum(rates.values()) - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_handles_missing_direction(self):
        """If a direction has zero counts, returns 0 for it."""
        from unittest.mock import AsyncMock, patch

        mock_rows = [
            {"actual_direction": "NEUTRAL", "cnt": 80},
            {"actual_direction": "BULLISH", "cnt": 20},
            # No BEARISH rows
        ]
        mock_db = AsyncMock()
        mock_db.fetch_all = AsyncMock(return_value=mock_rows)

        with patch("shared.neon.belief_queries.get_db", return_value=mock_db):
            from shared.neon.belief_queries import compute_empirical_base_rates

            rates = await compute_empirical_base_rates(days_back=90)

        assert rates["BEARISH"] == 0.0
        assert abs(rates["BULLISH"] - 0.20) < 0.001
        assert abs(rates["NEUTRAL"] - 0.80) < 0.001

    @pytest.mark.asyncio
    async def test_sums_to_one_with_any_distribution(self):
        """Output always sums to 1.0 regardless of input distribution."""
        from unittest.mock import AsyncMock, patch

        mock_rows = [
            {"actual_direction": "NEUTRAL", "cnt": 1},
            {"actual_direction": "BULLISH", "cnt": 1},
            {"actual_direction": "BEARISH", "cnt": 1},
        ]
        mock_db = AsyncMock()
        mock_db.fetch_all = AsyncMock(return_value=mock_rows)

        with patch("shared.neon.belief_queries.get_db", return_value=mock_db):
            from shared.neon.belief_queries import compute_empirical_base_rates

            rates = await compute_empirical_base_rates(days_back=90)

        assert abs(sum(rates.values()) - 1.0) < 0.001


class TestAgentPredictionVsActual:
    """Test compute_agent_prediction_vs_actual (combined query)."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_data(self):
        from unittest.mock import AsyncMock, patch

        mock_db = AsyncMock()
        mock_db.fetch_all = AsyncMock(return_value=[])

        with patch("shared.neon.belief_queries.get_db", return_value=mock_db):
            from shared.neon.belief_queries import compute_agent_prediction_vs_actual

            predicted, actual = await compute_agent_prediction_vs_actual(
                "sector_news", days_back=30
            )

        assert predicted == {}
        assert actual == {}

    @pytest.mark.asyncio
    async def test_computes_both_distributions(self):
        from unittest.mock import AsyncMock, patch

        # Cross-tab: direction × actual_direction
        mock_rows = [
            {"direction": "BULLISH", "actual_direction": "NEUTRAL", "cnt": 15},
            {"direction": "BULLISH", "actual_direction": "BULLISH", "cnt": 8},
            {"direction": "NEUTRAL", "actual_direction": "NEUTRAL", "cnt": 50},
            {"direction": "NEUTRAL", "actual_direction": "BULLISH", "cnt": 3},
            {"direction": "BEARISH", "actual_direction": "NEUTRAL", "cnt": 14},
            {"direction": "BEARISH", "actual_direction": "BEARISH", "cnt": 10},
        ]
        mock_db = AsyncMock()
        mock_db.fetch_all = AsyncMock(return_value=mock_rows)

        with patch("shared.neon.belief_queries.get_db", return_value=mock_db):
            from shared.neon.belief_queries import compute_agent_prediction_vs_actual

            predicted, actual = await compute_agent_prediction_vs_actual(
                "sector_news", days_back=30
            )

        # Total: 100
        # Predicted: BULLISH=23, NEUTRAL=53, BEARISH=24
        assert abs(predicted["BULLISH"] - 0.23) < 0.01
        assert abs(predicted["NEUTRAL"] - 0.53) < 0.01
        assert abs(predicted["BEARISH"] - 0.24) < 0.01
        assert abs(sum(predicted.values()) - 1.0) < 0.001

        # Actual: NEUTRAL=79, BULLISH=11, BEARISH=10
        assert abs(actual["NEUTRAL"] - 0.79) < 0.01
        assert abs(actual["BULLISH"] - 0.11) < 0.01
        assert abs(actual["BEARISH"] - 0.10) < 0.01
        assert abs(sum(actual.values()) - 1.0) < 0.001


class TestOutcomeReinforcementFormat:
    """Test _format_stats produces correct warnings."""

    def test_direction_alert_below_40(self):
        from pipeline.outcome_reinforcement import _format_stats

        stats = {
            "scored_beliefs": 50,
            "direction_accuracy": 0.35,
            "avg_conviction": 0.55,
            "brier_30d": 0.62,
            "reversals": 2,
        }
        result = _format_stats(stats)
        assert "DIRECTION ALERT" in result
        assert "near-random" in result
        assert "+/-1.5%" in result

    def test_no_direction_alert_above_40(self):
        from pipeline.outcome_reinforcement import _format_stats

        stats = {
            "scored_beliefs": 50,
            "direction_accuracy": 0.48,
            "avg_conviction": 0.55,
            "brier_30d": 0.45,
            "reversals": 2,
        }
        result = _format_stats(stats)
        assert "DIRECTION ALERT" not in result

    def test_conviction_cap_above_050_brier(self):
        from pipeline.outcome_reinforcement import _format_stats

        stats = {
            "scored_beliefs": 50,
            "direction_accuracy": 0.45,
            "avg_conviction": 0.60,
            "brier_30d": 0.55,
            "reversals": 1,
        }
        result = _format_stats(stats)
        assert "CONVICTION CAP" in result
        assert "0.50" in result

    def test_no_conviction_cap_below_050_brier(self):
        from pipeline.outcome_reinforcement import _format_stats

        stats = {
            "scored_beliefs": 50,
            "direction_accuracy": 0.55,
            "avg_conviction": 0.60,
            "brier_30d": 0.40,
            "reversals": 1,
        }
        result = _format_stats(stats)
        assert "CONVICTION CAP" not in result

    def test_both_warnings_fire_together(self):
        from pipeline.outcome_reinforcement import _format_stats

        stats = {
            "scored_beliefs": 100,
            "direction_accuracy": 0.30,
            "avg_conviction": 0.65,
            "brier_30d": 0.65,
            "reversals": 5,
        }
        result = _format_stats(stats)
        assert "DIRECTION ALERT" in result
        assert "CONVICTION CAP" in result
        assert "NEEDS IMPROVEMENT" in result
