"""Unit tests for get_position_scale_factor() in agents/tools/portfolio.py.

Tests the win-rate sizing ladder and geopolitical shock multiplier.
All async dependencies are mocked — no DB needed.
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from agents.tools.portfolio import get_position_scale_factor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_learnings_summary(overall_win_rate: float) -> dict:
    return {"overall_win_rate": overall_win_rate}


# ---------------------------------------------------------------------------
# Win-rate tier tests (no geo shock)
# ---------------------------------------------------------------------------


class TestWinRateTiers:
    """Scale ladder: full=1.0, reduced=0.85, half=0.7, floor=max(0.25, 0.5)=0.5."""

    @pytest.mark.asyncio
    async def test_high_win_rate_full_scale(self, mock_trading_config):
        """win_rate >= 50 -> scale = 1.0."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(55.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        assert result["scale_factor"] == 1.0
        assert result["win_rate"] == 55.0
        assert result["shock_multiplier"] == 1.0

    @pytest.mark.asyncio
    async def test_moderate_win_rate_reduced_scale(self, mock_trading_config):
        """35 <= win_rate < 50 -> scale = 0.85."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(42.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        assert result["scale_factor"] == 0.85
        assert result["win_rate"] == 42.0

    @pytest.mark.asyncio
    async def test_low_win_rate_half_scale(self, mock_trading_config):
        """20 <= win_rate < 35 -> scale = 0.7."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(25.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        assert result["scale_factor"] == 0.7
        assert result["win_rate"] == 25.0

    @pytest.mark.asyncio
    async def test_very_low_win_rate_floor_scale(self, mock_trading_config):
        """win_rate < 20 -> scale = max(minimal_scale_factor=0.25, 0.5) = 0.5."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(10.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        # Default minimal_scale_factor=0.25 < 0.5, so floor is 0.5
        assert result["scale_factor"] == 0.5
        assert result["win_rate"] == 10.0


# ---------------------------------------------------------------------------
# Geopolitical shock multiplier tests
# ---------------------------------------------------------------------------


class TestGeopoliticalShockMultiplier:
    @pytest.mark.asyncio
    async def test_immediate_shock_halves_scale(self, mock_trading_config):
        """immediate_shock phase -> 0.5x multiplier applied to base scale."""
        geo_shock = {"phase_name": "immediate_shock", "id": 1}
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(60.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=geo_shock),
            ),
        ):
            result = await get_position_scale_factor()

        # base=1.0 * 0.5 = 0.5
        assert result["scale_factor"] == 0.5
        assert result["shock_multiplier"] == 0.5
        assert "immediate" in result["note"].lower()

    @pytest.mark.asyncio
    async def test_sustained_pressure_applies_075_multiplier(self, mock_trading_config):
        """sustained_pressure phase -> 0.75x multiplier applied to base scale."""
        geo_shock = {"phase_name": "sustained_pressure", "id": 2}
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(60.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=geo_shock),
            ),
        ):
            result = await get_position_scale_factor()

        # base=1.0 * 0.75 = 0.75
        assert result["scale_factor"] == 0.75
        assert result["shock_multiplier"] == 0.75
        assert "sustained" in result["note"].lower()

    @pytest.mark.asyncio
    async def test_no_shock_no_multiplier(self, mock_trading_config):
        """No active shock -> shock_multiplier stays 1.0."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(60.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        assert result["shock_multiplier"] == 1.0
        assert result["scale_factor"] == 1.0


# ---------------------------------------------------------------------------
# Combined win-rate + shock tests
# ---------------------------------------------------------------------------


class TestCombinedScaling:
    @pytest.mark.asyncio
    async def test_moderate_win_rate_with_sustained_pressure(self, mock_trading_config):
        """35 <= win_rate < 50 (base=0.85) + sustained_pressure (0.75x) = 0.64."""
        geo_shock = {"phase_name": "sustained_pressure", "id": 3}
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(40.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=geo_shock),
            ),
        ):
            result = await get_position_scale_factor()

        assert result["scale_factor"] == round(0.85 * 0.75, 2)
        assert result["shock_multiplier"] == 0.75
        assert result["win_rate"] == 40.0


# ---------------------------------------------------------------------------
# Error fallback
# ---------------------------------------------------------------------------


class TestErrorFallback:
    @pytest.mark.asyncio
    async def test_exception_returns_safe_default(self, mock_trading_config):
        """Any exception -> fallback to 0.75x scale with error note."""
        with patch(
            "agents.tools.portfolio._get_learnings_summary_async",
            new=AsyncMock(side_effect=RuntimeError("DB unavailable")),
        ):
            result = await get_position_scale_factor()

        assert result["scale_factor"] == 0.75
        assert result["win_rate"] == 0
        assert result["shock_multiplier"] == 1.0
        assert "error" in result["prose"].lower()


# ---------------------------------------------------------------------------
# No learnings summary -> default win rate
# ---------------------------------------------------------------------------


class TestNoLearningsSummary:
    @pytest.mark.asyncio
    async def test_none_summary_defaults_to_50_percent(self, mock_trading_config):
        """_get_learnings_summary_async returns None -> win_rate defaults to 50 -> scale=1.0."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        # win_rate defaults to 50 >= full_winrate_threshold(50) -> 1.0
        assert result["win_rate"] == 50
        assert result["scale_factor"] == 1.0

    @pytest.mark.asyncio
    async def test_missing_key_in_summary_defaults_to_50_percent(self, mock_trading_config):
        """Summary dict without overall_win_rate key -> defaults to 50 -> scale=1.0."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value={"other_key": 99}),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        assert result["win_rate"] == 50
        assert result["scale_factor"] == 1.0


# ---------------------------------------------------------------------------
# Boundary: exactly at threshold values
# ---------------------------------------------------------------------------


class TestBoundaryThresholds:
    @pytest.mark.asyncio
    async def test_exactly_at_full_winrate_threshold(self, mock_trading_config):
        """win_rate == 50.0 exactly -> scale = 1.0 (>= full threshold)."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(50.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        assert result["scale_factor"] == 1.0

    @pytest.mark.asyncio
    async def test_exactly_at_reduced_winrate_threshold(self, mock_trading_config):
        """win_rate == 35.0 exactly -> scale = 0.85 (>= reduced threshold, < full)."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(35.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        assert result["scale_factor"] == 0.85

    @pytest.mark.asyncio
    async def test_exactly_at_half_winrate_threshold(self, mock_trading_config):
        """win_rate == 20.0 exactly -> scale = 0.7 (>= half threshold, < reduced)."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(20.0)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        assert result["scale_factor"] == 0.7

    @pytest.mark.asyncio
    async def test_one_below_half_threshold_hits_floor(self, mock_trading_config):
        """win_rate == 19.9 -> below half threshold -> floor scale = 0.5."""
        with (
            patch(
                "agents.tools.portfolio._get_learnings_summary_async",
                new=AsyncMock(return_value=_make_learnings_summary(19.9)),
            ),
            patch(
                "shared.neon.catalyst_summaries.get_active_geopolitical_shock",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await get_position_scale_factor()

        assert result["scale_factor"] == 0.5
