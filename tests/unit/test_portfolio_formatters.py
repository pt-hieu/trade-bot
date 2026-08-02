"""Unit tests for portfolio prose formatters."""

import pytest

from agents.tools.portfolio_formatters import (
    _enrich_holding,
    _format_cash_prose,
    _format_goal_prose,
    _format_holdings_prose,
    _format_pct,
    _format_price_k,
    _format_trades_for_date_prose,
    _format_trades_prose,
    _format_watchlist_prose,
)
from agents.tools.portfolio_learnings import _get_sector_bias, _get_ticker_accuracy
from shared.formatting import format_vnd as _format_vnd

# ── _format_vnd ────────────────────────────────────────────────────────────


class TestFormatVnd:
    @pytest.mark.parametrize(
        "amount,expected",
        [
            (1_500_000_000, "1.5B"),
            (85_500_000, "85.5M"),
            (1_000_000, "1.0M"),
            (5_200, "5.2k"),
            (500, "500"),
            (0, "0"),
        ],
    )
    def test_format_amounts(self, amount, expected):
        assert _format_vnd(amount) == expected


# ── _format_price_k ───────────────────────────────────────────────────────


class TestFormatPriceK:
    @pytest.mark.parametrize(
        "price,expected",
        [
            (93000, "93.0k"),
            (35900, "35.9k"),
            (500, "0.5k"),
            (0, "N/A"),
            (None, "N/A"),
        ],
    )
    def test_format_prices(self, price, expected):
        assert _format_price_k(price) == expected


# ── _format_pct ────────────────────────────────────────────────────────────


class TestFormatPct:
    @pytest.mark.parametrize(
        "pct,expected",
        [
            (4.3, "+4.3%"),
            (-2.1, "-2.1%"),
            (0.0, "+0.0%"),
            (100.0, "+100.0%"),
        ],
    )
    def test_format_percentages(self, pct, expected):
        assert _format_pct(pct) == expected


# ── _enrich_holding ───────────────────────────────────────────────────────


class TestEnrichHolding:
    def _make_holding(self, ticker: str = "TCB", **overrides) -> dict:
        """Build a complete HoldingData dict with sensible defaults."""
        base = {
            "ticker": ticker,
            "plan_type": "SWING",
            "shares": 500,
            "avg_cost": 35900,
            "avg_cost_vnd": 35900.0,
            "type": "Stock",
            "current_price_vnd": 37500,
            "market_value": 18750000.0,
            "slice_weight_pct": 25.0,
            "ticker_weight_pct": 25.0,
            "pct_from_entry": 4.5,
            "breakeven_stop": 34000,
        }
        base.update(overrides)
        return base

    def test_adds_all_display_strings(self):
        data = self._make_holding()
        result = _enrich_holding(data)
        assert "pct_from_entry_str" in result
        assert "slice_weight_pct_str" in result
        assert "ticker_weight_pct_str" in result
        assert "entry_price_str" in result
        assert "current_price_str" in result

    def test_positive_change(self):
        data = self._make_holding()
        result = _enrich_holding(data)
        assert result["pct_from_entry_str"] == "+4.5%"
        assert result["slice_weight_pct_str"] == "25.0%"

    def test_negative_change(self):
        data = self._make_holding(
            ticker="NLG",
            avg_cost=35900,
            current_price_vnd=34000,
            slice_weight_pct=15.0,
            ticker_weight_pct=15.0,
            pct_from_entry=-5.3,
        )
        result = _enrich_holding(data)
        assert result["pct_from_entry_str"] == "-5.3%"


# ── _format_holdings_prose ────────────────────────────────────────────────


class TestFormatHoldingsProse:
    def test_empty_holdings(self):
        assert _format_holdings_prose([]) == "No positions currently held."

    def test_single_holding(self, mock_trading_config):
        holdings = [
            {
                "ticker": "TCB",
                "plan_type": "SWING",
                "shares": 200,
                "avg_cost": 35900,
                "current_price_vnd": 37500,
                "slice_weight_pct": 50.0,
                "ticker_weight_pct": 50.0,
                "pct_from_entry": 4.5,
                "breakeven_stop": 35000,
            }
        ]
        result = _format_holdings_prose(holdings)
        assert "TCB" in result
        assert "200 shares" in result
        assert "SWING" in result

    def test_high_concentration_flagged(self, mock_trading_config):
        holdings = [
            {
                "ticker": "FPT",
                "plan_type": "LONGTERM",
                "shares": 100,
                "avg_cost": 95000,
                "current_price_vnd": 100000,
                "slice_weight_pct": 35.0,
                "ticker_weight_pct": 35.0,
                "pct_from_entry": 5.3,
                "breakeven_stop": 90000,
            }
        ]
        result = _format_holdings_prose(holdings)
        assert "HIGH concentration" in result


# ── _format_cash_prose ────────────────────────────────────────────────────


class TestFormatCashProse:
    def test_can_trade(self, mock_trading_config):
        cash = {
            "total_cash": 80_000_000,
            "min_reserve": 10_000_000,
            "deployable": 70_000_000,
            "can_trade": True,
        }
        result = _format_cash_prose(cash)
        assert "Trading allowed" in result
        assert "80.0M" in result

    def test_cannot_trade(self, mock_trading_config):
        cash = {
            "total_cash": 45_000_000,
            "min_reserve": 10_000_000,
            "deployable": 0,
            "can_trade": False,
        }
        result = _format_cash_prose(cash)
        assert "Insufficient" in result


# ── _format_goal_prose ────────────────────────────────────────────────────


class TestFormatGoalProse:
    def test_on_track(self):
        goal = {
            "name": "Jan 2026",
            "target": 5_000_000,
            "realized": 3_000_000,
            "remaining": 2_000_000,
            "progress_pct": 60.0,
            "days_left": 10,
            "daily_target": 200_000,
            "on_track": True,
        }
        result = _format_goal_prose(goal)
        assert "On track" in result
        assert "Jan 2026" in result

    def test_behind_schedule(self):
        goal = {
            "name": "Feb 2026",
            "target": 5_000_000,
            "realized": 500_000,
            "remaining": 4_500_000,
            "progress_pct": 10.0,
            "days_left": 5,
            "daily_target": 900_000,
            "on_track": False,
        }
        result = _format_goal_prose(goal)
        assert "Behind schedule" in result


# ── _format_trades_prose ──────────────────────────────────────────────────


class TestFormatTradesProse:
    def test_empty_trades(self):
        assert _format_trades_prose([]) == "No recent trades."

    def test_closed_trade(self):
        trades = [
            {
                "ticker": "TCB",
                "entry_date": "2026-01-10",
                "entry_price": 35900,
                "exit_price": 38000,
                "status": "CLOSED",
                "strategy": "bounce",
                "pl_pct": 5.8,
            }
        ]
        result = _format_trades_prose(trades)
        assert "WIN" in result
        assert "+5.8%" in result

    def test_open_trade(self):
        trades = [
            {
                "ticker": "FPT",
                "entry_date": "2026-01-15",
                "entry_price": 95000,
                "status": "OPEN",
                "strategy": "trend",
            }
        ]
        result = _format_trades_prose(trades)
        assert "OPEN" in result


# ── _format_trades_for_date_prose ─────────────────────────────────────────


class TestFormatTradesForDateProse:
    def test_no_trades(self):
        result = _format_trades_for_date_prose({"opened": [], "closed": []})
        assert "No trades" in result

    def test_opened_and_closed(self):
        data = {
            "opened": [{"ticker": "TCB", "entry_price": 35900, "shares": 200}],
            "closed": [{"ticker": "FPT", "exit_price": 95000, "pl_pct": 3.5}],
        }
        result = _format_trades_for_date_prose(data)
        assert "Opened 1" in result
        assert "Closed 1" in result


# ── _format_watchlist_prose ───────────────────────────────────────────────


class TestFormatWatchlistProse:
    def test_grouped_by_conviction(self):
        watchlist = {
            "FPT": {"conviction": "high", "entry_zone": 95000, "sector": "Tech"},
            "VHM": {"conviction": "medium", "entry_zone": 115000, "sector": "RE"},
            "NLG": {"conviction": "low", "entry_zone": 32000, "sector": "RE"},
        }
        result = _format_watchlist_prose(watchlist)
        assert "HIGH conviction" in result
        assert "MEDIUM conviction" in result
        assert "FPT" in result

    def test_empty_watchlist(self):
        assert _format_watchlist_prose({}) == "No stocks in watchlist."


# ── _get_sector_bias / _get_ticker_accuracy ───────────────────────────────


class TestSectorBias:
    def test_hot_and_cold(self):
        insights = [
            {"sector": "Banking", "bias": "Strong bullish"},
            {"sector": "Real Estate", "bias": "Weak bearish"},
            {"sector": "Tech", "bias": "neutral"},
        ]
        result = _get_sector_bias(insights, None)
        assert "Banking" in result["hot"]
        assert "Real Estate" in result["cold"]

    def test_filter_by_sector(self):
        insights = [
            {"sector": "Banking", "bias": "bullish"},
            {"sector": "Tech", "bias": "bearish"},
        ]
        result = _get_sector_bias(insights, "banking")
        assert len(result["data"]) == 1


class TestTickerAccuracy:
    def test_high_and_low(self):
        insights = [
            {"ticker": "FPT", "recent_accuracy": 80},
            {"ticker": "TCB", "recent_accuracy": 25},
            {"ticker": "VHM", "recent_accuracy": 50},
        ]
        result = _get_ticker_accuracy(insights, None)
        assert "FPT" in result["high"]
        assert "TCB" in result["low"]

    def test_filter_by_ticker(self):
        insights = [
            {"ticker": "FPT", "recent_accuracy": 80},
            {"ticker": "TCB", "recent_accuracy": 25},
        ]
        result = _get_ticker_accuracy(insights, "fpt")
        assert len(result["data"]) == 1
