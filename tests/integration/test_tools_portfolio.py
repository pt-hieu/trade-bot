"""
Integration tests for scripts/agents/tools/portfolio.py with database mocking.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.usefixtures("mock_trading_config")
class TestGetHoldingsAsync:
    """Tests for get_holdings_async function with database mocking."""

    @pytest.mark.asyncio
    async def test_returns_holdings(self, mock_portfolio_holdings):
        """Should return holdings from database."""
        with patch(
            "agents.tools.portfolio._get_portfolio_holdings_async",
            new_callable=AsyncMock,
            return_value=mock_portfolio_holdings,
        ):
            from agents.tools.portfolio import get_holdings_async

            result = await get_holdings_async()

            assert "holdings" in result
            tickers = [slice_row["ticker"] for slice_row in result["holdings"]]
            assert "NLG" in tickers
            nlg_slice = next(
                slice_row for slice_row in result["holdings"] if slice_row["ticker"] == "NLG"
            )
            assert nlg_slice["shares"] == 1000

    @pytest.mark.asyncio
    async def test_returns_error_on_empty(self):
        """Should return error when no holdings."""
        with patch(
            "agents.tools.portfolio._get_portfolio_holdings_async",
            new_callable=AsyncMock,
            return_value=[],
        ):
            from agents.tools.portfolio import get_holdings_async

            result = await get_holdings_async()

            assert "error" in result

    @pytest.mark.asyncio
    async def test_returns_error_on_exception(self):
        """Should return error on database exception."""
        with patch(
            "agents.tools.portfolio._get_portfolio_holdings_async",
            new_callable=AsyncMock,
            side_effect=Exception("Connection failed"),
        ):
            from agents.tools.portfolio import get_holdings_async

            result = await get_holdings_async()

            assert "error" in result
            assert "Connection failed" in result["error"]


@pytest.mark.usefixtures("mock_trading_config")
class TestGetCashBalanceAsync:
    """Tests for get_cash_balance_async function with database mocking."""

    @pytest.mark.asyncio
    async def test_returns_cash_balance(self):
        """Should return cash balance from database."""
        with patch(
            "agents.tools.portfolio._get_cash_balance_async",
            new_callable=AsyncMock,
            return_value=80_000_000,
        ):
            from agents.tools.portfolio import get_cash_balance_async

            result = await get_cash_balance_async()

            assert result["total_cash"] == 80_000_000
            assert result["min_reserve"] == 10_000_000
            assert result["deployable"] == 70_000_000
            assert result["can_trade"] is True

    @pytest.mark.asyncio
    async def test_low_cash_scenario(self):
        """Should handle low cash scenario."""
        with patch(
            "agents.tools.portfolio._get_cash_balance_async",
            new_callable=AsyncMock,
            return_value=12_000_000,
        ):
            from agents.tools.portfolio import get_cash_balance_async

            result = await get_cash_balance_async()

            assert result["deployable"] == 2_000_000
            assert result["can_trade"] is False


class TestGetLongtermWatchlistAsync:
    """Tests for get_longterm_watchlist_async function with database mocking."""

    @pytest.mark.asyncio
    async def test_returns_all_watchlist(self, mock_longterm_watchlist):
        """Should return full watchlist."""
        with patch(
            "agents.tools.portfolio._get_longterm_watchlist_async",
            new_callable=AsyncMock,
            return_value=mock_longterm_watchlist,
        ):
            from agents.tools.portfolio import get_longterm_watchlist_async

            result = await get_longterm_watchlist_async()

            assert "FPT" in result["watchlist"]
            assert "TCB" in result["watchlist"]
            assert len(result["watchlist"]) == 3

    @pytest.mark.asyncio
    async def test_filters_high_conviction(self, mock_longterm_watchlist):
        """Should filter to high conviction stocks only."""
        with patch(
            "agents.tools.portfolio._get_longterm_watchlist_async",
            new_callable=AsyncMock,
            return_value=mock_longterm_watchlist,
        ):
            from agents.tools.portfolio import get_longterm_watchlist_async

            result = await get_longterm_watchlist_async(filter_type="high_conviction")

            assert "FPT" in result["watchlist"]
            assert "TCB" in result["watchlist"]
            assert "VHM" in result["watchlist"]

    @pytest.mark.asyncio
    async def test_filters_by_sector(self, mock_longterm_watchlist):
        """Should filter by sector."""
        with patch(
            "agents.tools.portfolio._get_longterm_watchlist_async",
            new_callable=AsyncMock,
            return_value=mock_longterm_watchlist,
        ):
            from agents.tools.portfolio import get_longterm_watchlist_async

            result = await get_longterm_watchlist_async(filter_type="by_sector", sector="Banking")

            assert "TCB" in result["watchlist"]
            assert "FPT" not in result["watchlist"]


class TestGetRecentTradesAsync:
    """Tests for get_recent_trades_async function with database mocking."""

    @pytest.mark.asyncio
    async def test_returns_trades(self, mock_trades):
        """Should return recent trades."""
        with patch(
            "agents.tools.portfolio._get_recent_trades_async",
            new_callable=AsyncMock,
            return_value=mock_trades,
        ):
            from agents.tools.portfolio import get_recent_trades_async

            result = await get_recent_trades_async(limit=5)

            assert len(result["trades"]) == 2
            assert result["trades"][0]["ticker"] == "TCB"


@pytest.mark.usefixtures("mock_trading_config")
class TestGetGoalProgressAsync:
    """Tests for get_goal_progress_async function with database mocking."""

    @pytest.mark.asyncio
    async def test_returns_goal_progress(self, mock_active_goal):
        """Should return goal progress with calculated fields."""
        mock_cash = {
            "total_cash": 80_000_000,
            "min_reserve": 10_000_000,
            "deployable": 70_000_000,
            "can_trade": True,
        }
        with (
            patch(
                "agents.tools.portfolio._get_active_goal_async",
                new_callable=AsyncMock,
                return_value=mock_active_goal,
            ),
            patch(
                "agents.tools.portfolio.get_cash_balance_async",
                new_callable=AsyncMock,
                return_value=mock_cash,
            ),
            patch(
                "agents.tools.portfolio._get_swing_trade_stats_async",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            from agents.tools.portfolio import get_goal_progress_async

            result = await get_goal_progress_async()

            assert result["name"] == "January 2026"
            assert result["target"] == 5_000_000
            assert result["realized"] == 1_500_000
            assert result["remaining"] == 3_500_000
            assert result["progress_pct"] == 30.0

    @pytest.mark.asyncio
    async def test_returns_error_when_no_goal(self):
        """Should return error when no active goal."""
        with patch(
            "agents.tools.portfolio._get_active_goal_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from agents.tools.portfolio import get_goal_progress_async

            result = await get_goal_progress_async()

            assert "error" in result


class TestGetLearningsAsync:
    """Tests for get_learnings_async function with database mocking."""

    @pytest.mark.asyncio
    async def test_summary_query(self, sample_learnings):
        """Should return summary from database."""
        with patch(
            "agents.tools.portfolio_learnings._get_learnings_summary_async",
            new_callable=AsyncMock,
            return_value=sample_learnings.get("summary", {}),
        ):
            from agents.tools.portfolio import get_learnings_async

            result = await get_learnings_async(query="summary")

            assert result["query"] == "summary"
            assert result["data"]["total_days"] == 10

    @pytest.mark.asyncio
    async def test_sector_bias_query(self, sample_learnings):
        """Should return sector bias from database."""
        with patch(
            "agents.tools.portfolio_learnings._get_sector_insights_async",
            new_callable=AsyncMock,
            return_value=sample_learnings.get("sector_insights", []),
        ):
            from agents.tools.portfolio import get_learnings_async

            result = await get_learnings_async(query="sector_bias")

            assert result["query"] == "sector_bias"
            assert "hot" in result
            assert "cold" in result

    @pytest.mark.asyncio
    async def test_returns_error_on_invalid_query(self):
        """Should return error for unknown query type."""
        from agents.tools.portfolio import get_learnings_async

        result = await get_learnings_async(query="invalid_query")

        assert "error" in result
