"""Tests for deterministic retrospective evaluation — summary."""

import pytest

from agents.retro.compute import compute_day_summary, compute_evaluations

pytestmark = pytest.mark.usefixtures("mock_trading_config")


class TestDaySummary:
    """Day summary excludes EXCLUDED actions from stats."""

    def test_excludes_skip_from_win_rate(self):
        """AVOID/WAIT excluded from total_recs; only scoreable evals count."""
        prices = {
            "VHM": {"open": 95.0, "high": 101.0, "low": 94.5, "close": 100.7, "volume": 8000000},
        }
        recs = [
            {
                "ticker": "VHM",
                "action": "BUY",
                "entry_price": 95000,
                "stop_price": 93000,
                "target_price": 101000,
            },  # WIN
            {"ticker": "GAS", "action": "AVOID"},
            {"ticker": "FPT", "action": "WAIT"},
        ]
        evals = compute_evaluations(recs, prices)
        summary = compute_day_summary(evals)
        # Only VHM counts (WIN); AVOID and WAIT excluded
        assert summary["total_recs"] == 1

    def test_entry_hit_rate_buy_only(self, eod_prices):
        recs = [
            {
                "ticker": "HDB",
                "action": "BUY",
                "entry_price": 26800,
                "stop_price": 26200,
                "target_price": 30000,
            },  # entry hit
            {
                "ticker": "TCB",
                "action": "BUY",
                "entry_price": 34000,
                "stop_price": 33000,
                "target_price": 38000,
            },  # entry missed
        ]
        evals = compute_evaluations(recs, eod_prices)
        summary = compute_day_summary(evals)
        assert summary["entry_hit_rate"] == 50.0  # 1/2

    def test_best_worst_call(self, eod_prices):
        holdings = [
            {"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 90_000},
            {"ticker": "GAS", "plan_type": "SWING", "avg_cost_vnd": 78_000},
        ]
        recs = [
            {"ticker": "VHM", "action": "HOLD"},  # positive from entry
            {"ticker": "GAS", "action": "HOLD"},  # negative from entry
        ]
        evals = compute_evaluations(recs, eod_prices, holdings=holdings)
        summary = compute_day_summary(evals)
        assert "VHM" in summary["best_call"]
        assert "GAS" in summary["worst_call"]

    def test_empty_evaluations(self):
        summary = compute_day_summary([])
        assert summary["total_recs"] == 0
        assert summary["win_rate"] == 0.0
        assert summary["best_call"] == "None"

    def test_all_excluded(self, eod_prices):
        recs = [
            {"ticker": "GAS", "action": "AVOID"},
            {"ticker": "VHM", "action": "SKIP"},
        ]
        evals = compute_evaluations(recs, eod_prices)
        summary = compute_day_summary(evals)
        assert summary["total_recs"] == 0
        assert summary["win_rate"] == 0.0

    def test_hold_without_entry_excluded_from_win_rate(self):
        """HOLD without portfolio data excluded from win rate totals."""
        prices = {
            "VHM": {"open": 95.0, "high": 101.0, "low": 94.5, "close": 100.7, "volume": 8000000},
            "TCB": {"open": 34.85, "high": 35.9, "low": 34.8, "close": 35.9, "volume": 11603200},
        }
        recs = [
            {
                "ticker": "VHM",
                "action": "BUY",
                "entry_price": 95000,
                "stop_price": 93000,
                "target_price": 101000,
            },  # WIN
            {"ticker": "TCB", "action": "HOLD"},  # no holdings → excluded
        ]
        evals = compute_evaluations(recs, prices, holdings=[])
        summary = compute_day_summary(evals)
        assert summary["total_recs"] == 1  # TCB HOLD without entry data not counted

    def test_hold_with_entry_included_in_win_rate(self, eod_prices):
        """HOLD with portfolio entry data counts as win when P/L > 0."""
        holdings = [
            {"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 90_000}
        ]  # VHM close=100,700 → win
        recs = [{"ticker": "VHM", "action": "HOLD"}]
        evals = compute_evaluations(recs, eod_prices, holdings=holdings)
        summary = compute_day_summary(evals)
        assert summary["total_recs"] == 1
        assert summary["win_rate"] == 100.0

    def test_hold_with_entry_loss_not_counted_as_win(self, eod_prices):
        """HOLD with P/L < 0 from entry is not a win."""
        holdings = [
            {"ticker": "GAS", "plan_type": "SWING", "avg_cost_vnd": 78_000}
        ]  # GAS close=75,500 → loss
        recs = [{"ticker": "GAS", "action": "HOLD"}]
        evals = compute_evaluations(recs, eod_prices, holdings=holdings)
        summary = compute_day_summary(evals)
        assert summary["win_rate"] == 0.0

    def test_missed_tickers_excluded_from_win_rate(self):
        """MISSED tickers (no price data) must not inflate win_rate denominator."""
        # VHM: entry=95k, low=94.5k → hit, target=101k, high=101k → target hit → WIN
        prices = {
            "VHM": {"open": 95.0, "high": 101.0, "low": 94.5, "close": 100.7, "volume": 8000000},
        }
        recs = [
            {
                "ticker": "VHM",
                "action": "BUY",
                "entry_price": 95000,
                "stop_price": 93000,
                "target_price": 101000,
            },  # entry hit, target hit → WIN
            {
                "ticker": "FAKE1",
                "action": "BUY",
                "entry_price": 50000,
                "stop_price": 49000,
                "target_price": 55000,
            },  # no price data → MISSED
            {
                "ticker": "FAKE2",
                "action": "BUY",
                "entry_price": 60000,
                "stop_price": 59000,
                "target_price": 65000,
            },  # no price data → MISSED
        ]
        evals = compute_evaluations(recs, prices)
        summary = compute_day_summary(evals)
        # Only VHM counts (1 rec, 1 win); FAKE1/FAKE2 excluded as MISSED
        assert summary["total_recs"] == 1
        assert summary["win_rate"] == 100.0  # not 33.3%


# ============================================================================
# day_change: prev_close vs open fallback
# ============================================================================


class TestDayChangePrevClose:
    """day_change should use prev_close when available, not open."""

    def test_day_change_uses_prev_close(self):
        """VHM: prev_close=108, open=102.5, close=100.5 → day=-6.94% (not -1.95%)."""
        prices = {
            "VHM": {
                "open": 102.5,
                "high": 105.1,
                "low": 100.5,
                "close": 100.5,
                "volume": 6578000,
                "prev_close": 108.0,
            }
        }
        holdings = [{"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 93_000}]
        recs = [{"ticker": "VHM", "action": "TRIM"}]
        result = compute_evaluations(recs, prices, holdings=holdings)
        # day_change from prev_close: (100.5 - 108.0) / 108.0 * 100 = -6.94%
        assert result[0]["day_change"] is not None
        assert abs(result[0]["day_change"] - (-6.94)) < 0.1

    def test_day_change_falls_back_to_open(self):
        """Without prev_close, falls back to open→close."""
        prices = {
            "VHM": {"open": 102.5, "high": 105.1, "low": 100.5, "close": 100.5, "volume": 6578000}
        }
        holdings = [{"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 93_000}]
        recs = [{"ticker": "VHM", "action": "HOLD"}]
        result = compute_evaluations(recs, prices, holdings=holdings)
        # Fallback: (100.5 - 102.5) / 102.5 * 100 = -1.95%
        assert result[0]["day_change"] is not None
        assert abs(result[0]["day_change"] - (-1.95)) < 0.1

    def test_prev_close_none_falls_back(self):
        """prev_close=None uses open→close fallback."""
        prices = {
            "VHM": {
                "open": 102.5,
                "high": 105.1,
                "low": 100.5,
                "close": 100.5,
                "volume": 6578000,
                "prev_close": None,
            }
        }
        recs = [{"ticker": "VHM", "action": "HOLD"}]
        result = compute_evaluations(recs, prices)
        assert abs(result[0]["day_change"] - (-1.95)) < 0.1

    def test_prev_close_stored(self):
        """prev_close included in result dict for LLM context."""
        prices = {
            "VHM": {
                "open": 102.5,
                "high": 105.1,
                "low": 100.5,
                "close": 100.5,
                "volume": 6578000,
                "prev_close": 108.0,
            }
        }
        holdings = [{"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 93_000}]
        recs = [{"ticker": "VHM", "action": "TRIM"}]
        result = compute_evaluations(recs, prices, holdings=holdings)
        assert result[0]["prev_close"] == 108.0


# ============================================================================
# Win logic: TRIM/EXIT vs HOLD
# ============================================================================


class TestLongTermSection:
    """LONG_TERM watchlist items must be excluded from scoring."""

    @pytest.mark.parametrize("action", ["HOLD", "BUY", "WATCH", "WAIT"])
    def test_longterm_always_excluded(self, eod_prices, action):
        recs = [{"ticker": "VHM", "action": action, "section": "LONG_TERM"}]
        result = compute_evaluations(recs, eod_prices)
        assert result[0]["status"] == "EXCLUDED", (
            f"LONG_TERM {action} should be EXCLUDED, got {result[0]['status']}"
        )

    def test_longterm_hold_not_in_best_call(self, eod_prices):
        """LONG_TERM HOLD should not appear as best/worst call."""
        holdings = [
            {"ticker": "GAS", "plan_type": "SWING", "avg_cost_vnd": 78_000}
        ]  # real holding with entry data
        recs = [
            {"ticker": "VHM", "action": "HOLD", "section": "LONG_TERM"},  # watchlist
            {"ticker": "GAS", "action": "HOLD", "section": "HOLDINGS"},  # actual holding
        ]
        evals = compute_evaluations(recs, eod_prices, holdings=holdings)
        summary = compute_day_summary(evals)
        assert "VHM" not in summary["best_call"]
        assert "VHM" not in summary["worst_call"]
        assert summary["total_recs"] == 1  # only the real holding

    def test_longterm_excluded_from_win_rate(self, eod_prices):
        recs = [
            {"ticker": "VHM", "action": "HOLD", "section": "LONG_TERM"},
            {"ticker": "FPT", "action": "BUY", "entry_price": 98000, "section": "LONG_TERM"},
        ]
        evals = compute_evaluations(recs, eod_prices)
        summary = compute_day_summary(evals)
        assert summary["total_recs"] == 0
        assert summary["win_rate"] == 0.0


# ============================================================================
# compute_mode_compliance
# ============================================================================
