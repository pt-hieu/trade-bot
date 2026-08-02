"""Tests for deterministic retrospective evaluation — entry_evaluation."""

import pytest

from agents.retro.compute import compute_day_summary, compute_evaluations

pytestmark = pytest.mark.usefixtures("mock_trading_config")


class TestBuyEntryHit:
    """BUY where low <= entry_price → entry_hit = True."""

    def test_entry_hit(self, eod_prices):
        recs = [
            {
                "ticker": "HDB",
                "action": "BUY",
                "entry_price": 26800,
                "stop_price": 26200,
                "target_price": 30000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        # HDB low = 26.5k VND = 26500 <= 26800 → hit
        assert result[0]["entry_hit"] is True
        assert result[0]["status"] != "MISSED"

    def test_entry_missed(self, eod_prices):
        recs = [
            {
                "ticker": "TCB",
                "action": "BUY",
                "entry_price": 34000,
                "stop_price": 33000,
                "target_price": 38000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        # TCB low = 34.8k = 34800 > 34000 → missed
        assert result[0]["entry_hit"] is False
        assert result[0]["status"] == "MISSED"
        assert result[0]["pnl_percent"] == 0.0

    def test_entry_hit_exact(self, eod_prices):
        recs = [
            {
                "ticker": "TCB",
                "action": "BUY",
                "entry_price": 34800,
                "stop_price": 33000,
                "target_price": 38000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        # TCB low = 34.8k = 34800 == 34800 → hit (<=)
        assert result[0]["entry_hit"] is True


class TestStopHit:
    """Stop hit when entry_hit AND low <= stop_price."""

    def test_stop_triggered(self, eod_prices):
        recs = [
            {
                "ticker": "HDB",
                "action": "BUY",
                "entry_price": 26800,
                "stop_price": 26600,
                "target_price": 30000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        # HDB low = 26500 <= 26600 stop → stop hit
        assert result[0]["entry_hit"] is True
        assert result[0]["stop_hit"] is True
        assert result[0]["status"] == "LOSS"

    def test_stop_not_triggered(self, eod_prices):
        recs = [
            {
                "ticker": "HDB",
                "action": "BUY",
                "entry_price": 26800,
                "stop_price": 26200,
                "target_price": 30000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        # HDB low = 26500 > 26200 stop → stop not hit
        assert result[0]["stop_hit"] is False

    def test_stop_requires_entry_hit(self, eod_prices):
        recs = [
            {
                "ticker": "TCB",
                "action": "BUY",
                "entry_price": 34000,
                "stop_price": 35000,
                "target_price": 38000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        # Entry missed → stop can't be hit even if low < stop
        assert result[0]["entry_hit"] is False
        assert result[0]["stop_hit"] is False


class TestTargetHit:
    """Target hit when entry_hit AND high >= target_price."""

    def test_target_reached(self, eod_prices):
        recs = [
            {
                "ticker": "VHM",
                "action": "BUY",
                "entry_price": 95000,
                "stop_price": 93000,
                "target_price": 100500,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        # VHM low = 94500 <= 95000 → entry hit
        # VHM high = 101000 >= 100500 → target hit
        assert result[0]["entry_hit"] is True
        assert result[0]["target_hit"] is True
        assert result[0]["status"] == "WIN"

    def test_target_not_reached(self, eod_prices):
        recs = [
            {
                "ticker": "HDB",
                "action": "BUY",
                "entry_price": 26800,
                "stop_price": 26200,
                "target_price": 30000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        # HDB high = 27500 < 30000 → target not hit
        assert result[0]["target_hit"] is False


class TestPnlCalculation:
    """P/L = (close - entry) / entry * 100."""

    def test_positive_pnl(self, eod_prices):
        recs = [
            {
                "ticker": "HDB",
                "action": "BUY",
                "entry_price": 26800,
                "stop_price": 26200,
                "target_price": 30000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        # HDB close = 27200, entry = 26800
        # pnl = (27200 - 26800) / 26800 * 100 = 1.49%
        assert result[0]["entry_hit"] is True
        assert abs(result[0]["pnl_percent"] - 1.49) < 0.1

    def test_negative_pnl(self, eod_prices):
        recs = [
            {
                "ticker": "GAS",
                "action": "BUY",
                "entry_price": 80000,
                "stop_price": 74000,
                "target_price": 85000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        # GAS low = 75000 <= 80000 → entry hit
        # GAS close = 75500, entry = 80000
        # pnl = (75500 - 80000) / 80000 * 100 = -5.625%
        assert result[0]["entry_hit"] is True
        assert result[0]["pnl_percent"] < 0

    def test_no_pnl_when_missed(self, eod_prices):
        recs = [
            {
                "ticker": "TCB",
                "action": "BUY",
                "entry_price": 34000,
                "stop_price": 33000,
                "target_price": 38000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        assert result[0]["pnl_percent"] == 0.0


class TestExcludedActions:
    """SKIP/AVOID/WAIT/WATCH excluded from win rate."""

    @pytest.mark.parametrize("action", ["SKIP", "AVOID", "WAIT", "WATCH"])
    def test_excluded_status(self, eod_prices, action):
        recs = [{"ticker": "GAS", "action": action}]
        result = compute_evaluations(recs, eod_prices)
        assert result[0]["status"] == "EXCLUDED"
        assert result[0]["pnl_percent"] == 0.0
        assert result[0]["entry_hit"] is False

    def test_excluded_with_no_prices(self):
        recs = [{"ticker": "UNKNOWN", "action": "AVOID"}]
        result = compute_evaluations(recs, {})
        # No price data → still MISSED (not EXCLUDED) because we can't even check
        assert result[0]["status"] == "MISSED"


# ============================================================================
# compute_evaluations: HOLD/EXIT/TRIM → HOLD
# ============================================================================


class TestHoldActions:
    """HOLD/EXIT/TRIM compute P/L from portfolio entry price."""

    @pytest.fixture
    def holdings(self):
        """Portfolio holdings with entry prices in raw VND (list[HoldingData])."""
        return [
            {"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 90_000},
            {"ticker": "GAS", "plan_type": "SWING", "avg_cost_vnd": 78_000},
        ]

    @pytest.mark.parametrize("action", ["HOLD", "EXIT", "TRIM"])
    def test_hold_with_entry_data(self, eod_prices, holdings, action):
        recs = [{"ticker": "VHM", "action": action}]
        result = compute_evaluations(recs, eod_prices, holdings=holdings)
        assert result[0]["status"] == "HOLD"
        assert result[0]["has_entry_data"] is True
        # VHM close=100,700 VND, avg_cost=90,000 → +11.9%
        assert result[0]["pnl_percent"] > 10
        assert result[0]["day_change"] is not None

    def test_hold_without_entry_data(self, eod_prices):
        """HOLD on ticker not in portfolio → pnl_percent is None."""
        recs = [{"ticker": "VHM", "action": "HOLD"}]
        result = compute_evaluations(recs, eod_prices, holdings=[])
        assert result[0]["status"] == "HOLD"
        assert result[0]["pnl_percent"] is None
        assert result[0]["has_entry_data"] is False
        assert result[0]["day_change"] is not None

    def test_hold_no_holdings_arg(self, eod_prices):
        """Omitting holdings → pnl_percent is None (backward compat)."""
        recs = [{"ticker": "VHM", "action": "HOLD"}]
        result = compute_evaluations(recs, eod_prices)
        assert result[0]["pnl_percent"] is None
        assert result[0]["has_entry_data"] is False

    def test_hold_negative_from_entry(self, eod_prices, holdings):
        """HOLD where current price < avg_cost → negative P/L."""
        recs = [{"ticker": "GAS", "action": "HOLD"}]
        result = compute_evaluations(recs, eod_prices, holdings=holdings)
        # GAS close=75,500, avg_cost=78,000 → -3.2%
        assert result[0]["pnl_percent"] < 0
        assert result[0]["has_entry_data"] is True

    def test_hold_day_change_always_present(self, eod_prices, holdings):
        """day_change always populated for HOLD regardless of entry data."""
        recs = [{"ticker": "VHM", "action": "HOLD"}]
        result = compute_evaluations(recs, eod_prices, holdings=holdings)
        # VHM: open=95000, close=100700 → +6%
        assert result[0]["day_change"] is not None
        assert result[0]["day_change"] > 0


# ============================================================================
# compute_evaluations: Edge cases
# ============================================================================


class TestEdgeCases:
    """Missing data, no entry price, unknown ticker."""

    def test_missing_ticker(self, eod_prices):
        recs = [{"ticker": "NONEXISTENT", "action": "BUY", "entry_price": 50000}]
        result = compute_evaluations(recs, eod_prices)
        assert result[0]["status"] == "MISSED"

    def test_no_entry_price(self, eod_prices):
        recs = [{"ticker": "TCB", "action": "BUY", "entry_price": None}]
        result = compute_evaluations(recs, eod_prices)
        assert result[0]["status"] == "MISSED"

    def test_zero_entry_price(self, eod_prices):
        recs = [{"ticker": "TCB", "action": "BUY", "entry_price": 0}]
        result = compute_evaluations(recs, eod_prices)
        assert result[0]["status"] == "MISSED"

    def test_error_in_price_data(self):
        prices = {"TCB": {"error": "API timeout"}}
        recs = [{"ticker": "TCB", "action": "BUY", "entry_price": 34000}]
        result = compute_evaluations(recs, prices)
        assert result[0]["status"] == "MISSED"

    def test_zero_price_rejected(self):
        """Zero prices from failed fetch treated as MISSED."""
        prices = {"TCB": {"open": 0, "high": 0, "low": 0, "close": 0}}
        recs = [{"ticker": "TCB", "action": "BUY", "entry_price": 34000}]
        result = compute_evaluations(recs, prices)
        assert result[0]["status"] == "MISSED"
        assert "0" in result[0]["analysis"]

    def test_zero_price_hold_rejected(self):
        """Zero prices rejected even for HOLD actions."""
        prices = {"VHM": {"open": 0, "high": 0, "low": 0, "close": 0}}
        recs = [{"ticker": "VHM", "action": "HOLD"}]
        result = compute_evaluations(recs, prices)
        assert result[0]["status"] == "MISSED"

    def test_add_action_treated_as_entry(self, eod_prices):
        recs = [
            {
                "ticker": "HDB",
                "action": "ADD",
                "entry_price": 26800,
                "stop_price": 26200,
                "target_price": 30000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        assert result[0]["entry_hit"] is True

    def test_no_stop_price(self, eod_prices):
        recs = [
            {
                "ticker": "HDB",
                "action": "BUY",
                "entry_price": 26800,
                "stop_price": None,
                "target_price": 30000,
            }
        ]
        result = compute_evaluations(recs, eod_prices)
        assert result[0]["stop_hit"] is False  # Can't hit if no stop


# ============================================================================
# compute_day_summary
# ============================================================================


class TestTrimExitWinLogic:
    """TRIM/EXIT win logic uses day_change, not unrealized P/L."""

    def test_trim_stock_crash_not_win(self):
        """VHM TRIM + stock -6.9% → NOT a win (should have trimmed)."""
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
        evals = compute_evaluations(recs, prices, holdings=holdings)
        summary = compute_day_summary(evals)
        # pnl_percent is +8.06% from entry, but day_change is -6.94%
        assert evals[0]["pnl_percent"] > 0  # still positive from entry
        assert evals[0]["day_change"] < -3  # big daily drop
        assert summary["win_rate"] == 0.0  # NOT a win

    def test_trim_stock_up_is_win(self):
        """TRIM + stock rose → ignoring trim was ok → win."""
        prices = {
            "VHM": {
                "open": 95.0,
                "high": 101.0,
                "low": 94.5,
                "close": 100.7,
                "volume": 8000000,
                "prev_close": 95.0,
            }
        }
        holdings = [{"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 90_000}]
        recs = [{"ticker": "VHM", "action": "TRIM"}]
        evals = compute_evaluations(recs, prices, holdings=holdings)
        summary = compute_day_summary(evals)
        # day_change = (100700 - 95000) / 95000 = +6.0% → win (ignoring trim was fine)
        assert summary["win_rate"] == 100.0

    def test_exit_stock_drop_not_win(self):
        """EXIT + stock dropped → should have exited → not win."""
        prices = {
            "GAS": {
                "open": 80.0,
                "high": 80.5,
                "low": 75.0,
                "close": 75.5,
                "volume": 3000000,
                "prev_close": 82.0,
            }
        }
        holdings = [{"ticker": "GAS", "plan_type": "SWING", "avg_cost_vnd": 70_000}]
        recs = [{"ticker": "GAS", "action": "EXIT"}]
        evals = compute_evaluations(recs, prices, holdings=holdings)
        summary = compute_day_summary(evals)
        # day_change = (75500 - 82000) / 82000 = -7.93% → not win
        assert summary["win_rate"] == 0.0

    def test_hold_small_drop_still_win(self):
        """HOLD + stock -0.5% → minor move → still win."""
        prices = {
            "FPT": {
                "open": 99.0,
                "high": 99.5,
                "low": 98.0,
                "close": 98.5,
                "volume": 4000000,
                "prev_close": 99.0,
            }
        }
        holdings = [{"ticker": "FPT", "avg_cost_vnd": 85_000}]
        recs = [{"ticker": "FPT", "action": "HOLD"}]
        evals = compute_evaluations(recs, prices, holdings=holdings)
        summary = compute_day_summary(evals)
        # day_change = (98500 - 99000) / 99000 = -0.51% → >= -2.0 (default threshold) → win
        assert summary["win_rate"] == 100.0

    def test_hold_big_drop_not_win(self):
        """HOLD + stock -5% → bad hold → not win."""
        prices = {
            "GAS": {
                "open": 80.0,
                "high": 80.5,
                "low": 75.0,
                "close": 75.5,
                "volume": 3000000,
                "prev_close": 80.0,
            }
        }
        holdings = [{"ticker": "GAS", "plan_type": "SWING", "avg_cost_vnd": 78_000}]
        recs = [{"ticker": "GAS", "action": "HOLD"}]
        evals = compute_evaluations(recs, prices, holdings=holdings)
        summary = compute_day_summary(evals)
        # day_change = (75500 - 80000) / 80000 = -5.63% → not win
        assert summary["win_rate"] == 0.0


# ============================================================================
# best_call scoring: TRIM uses day_change
# ============================================================================


class TestBestCallScoring:
    """best_call uses day_change for HOLD actions, inverted for TRIM."""

    def test_trim_crash_not_best_call(self):
        """VHM TRIM with stock crash should NOT be best call despite high unrealized P/L."""
        prices = {
            "VHM": {
                "open": 102.5,
                "high": 105.1,
                "low": 100.5,
                "close": 100.5,
                "volume": 6578000,
                "prev_close": 108.0,
            },
            "FPT": {
                "open": 89.0,
                "high": 90.0,
                "low": 88.5,
                "close": 89.6,
                "volume": 4000000,
                "prev_close": 90.0,
            },
        }
        holdings = [
            {"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 93_000},
            {"ticker": "FPT", "plan_type": "SWING", "avg_cost_vnd": 92_000},
        ]
        recs = [
            {"ticker": "VHM", "action": "TRIM"},
            {"ticker": "FPT", "action": "HOLD"},
        ]
        evals = compute_evaluations(recs, prices, holdings=holdings)
        summary = compute_day_summary(evals)
        # VHM TRIM: score = -(-6.94) = +6.94 (stock dropping = good trim call)
        # FPT HOLD: score = day_change = -0.44%
        # VHM TRIM should be best (the recommendation was correct)
        assert "VHM" in summary["best_call"]
        # And it should show day change, not unrealized P/L
        assert "day:" in summary["best_call"]

    def test_best_call_format_hold(self):
        """HOLD best_call shows day change, not P/L from entry."""
        prices = {
            "VHM": {
                "open": 95.0,
                "high": 101.0,
                "low": 94.5,
                "close": 100.7,
                "volume": 8000000,
                "prev_close": 95.0,
            }
        }
        holdings = [{"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 90_000}]
        recs = [{"ticker": "VHM", "action": "HOLD"}]
        evals = compute_evaluations(recs, prices, holdings=holdings)
        summary = compute_day_summary(evals)
        assert "day:" in summary["best_call"]
        assert "VHM" in summary["best_call"]


# ============================================================================
# compute_evaluations: LONG_TERM section → EXCLUDED
# ============================================================================


class TestHoldStopBreach:
    """HOLD positions with stop_hit detection."""

    def test_hold_stop_breached(self):
        """HOLD with eod_low <= stop_price → STOP_BREACHED."""
        prices = {
            "VHM": {
                "open": 95.0,
                "high": 98.0,
                "low": 93.0,
                "close": 98.0,
                "prev_close": 96.0,
            }
        }
        holdings = [{"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 93_700}]
        recs = [
            {
                "ticker": "VHM",
                "action": "HOLD",
                "stop_price": 93700,  # VND integer → 93.7 k-VND
            }
        ]
        result = compute_evaluations(recs, prices, holdings=holdings)
        # eod_low=93.0 <= stop=93.7 → stop breached
        assert result[0]["stop_hit"] is True
        assert result[0]["status"] == "STOP_BREACHED"
        assert result[0]["pnl_percent"] is not None

    def test_hold_stop_not_breached(self):
        """HOLD with eod_low > stop_price → normal HOLD."""
        prices = {
            "VHM": {
                "open": 95.0,
                "high": 101.0,
                "low": 94.5,
                "close": 100.7,
                "prev_close": 95.0,
            }
        }
        holdings = [{"ticker": "VHM", "plan_type": "SWING", "avg_cost_vnd": 93_700}]
        recs = [
            {
                "ticker": "VHM",
                "action": "HOLD",
                "stop_price": 93700,  # 93.7 k-VND
            }
        ]
        result = compute_evaluations(recs, prices, holdings=holdings)
        # eod_low=94.5 > stop=93.7 → no breach
        assert result[0]["stop_hit"] is False
        assert result[0]["status"] == "HOLD"

    def test_hold_no_stop_price(self):
        """HOLD without stop_price → normal HOLD, stop_hit=False."""
        prices = {
            "FPT": {
                "open": 99.0,
                "high": 99.5,
                "low": 98.0,
                "close": 99.2,
                "prev_close": 99.0,
            }
        }
        recs = [{"ticker": "FPT", "action": "HOLD"}]
        result = compute_evaluations(recs, prices)
        assert result[0]["stop_hit"] is False
        assert result[0]["status"] == "HOLD"

    def test_evaluate_action_computes_stop_hit(self):
        """SWI-140: EVALUATE positions are still held — stop_hit must be evaluated.
        Replays today's ACV bundle: eod_low=43.9 <= stop=44.91 → stop_hit=True.
        Pre-fix this fell through the action catch-all and silently returned
        stop_hit=False, corrupting eval_critic ground truth."""
        prices = {
            "ACV": {
                "open": 44.5,
                "high": 45.0,
                "low": 43.9,
                "close": 44.0,
                "prev_close": 45.5,
            }
        }
        holdings = [{"ticker": "ACV", "plan_type": "SWING", "avg_cost_vnd": 45_000}]
        recs = [
            {
                "ticker": "ACV",
                "action": "EVALUATE",
                "stop_price": 44910,
            }
        ]
        result = compute_evaluations(recs, prices, holdings=holdings)
        assert result[0]["stop_hit"] is True
        assert result[0]["status"] == "STOP_BREACHED"

    def test_unknown_action_raises_loud(self):
        """SWI-140: Producer-side vocabulary additions must fail loud at the
        retro consumer instead of silently defaulting to status='HOLD'."""
        from agents.retro.won import UnknownActionError

        prices = {"FPT": {"open": 99.0, "high": 99.5, "low": 98.0, "close": 99.2}}
        recs = [{"ticker": "FPT", "action": "FOO_BAR_NEW_ACTION"}]
        with pytest.raises(UnknownActionError):
            compute_evaluations(recs, prices)

    def test_stop_breached_exact_boundary(self):
        """HOLD with eod_low == stop_price → STOP_BREACHED (<=)."""
        prices = {
            "TCB": {
                "open": 30.0,
                "high": 31.0,
                "low": 26.0,
                "close": 29.0,
                "prev_close": 30.0,
            }
        }
        holdings = [{"ticker": "TCB", "plan_type": "SWING", "avg_cost_vnd": 32_500}]
        recs = [
            {
                "ticker": "TCB",
                "action": "HOLD",
                "stop_price": 26000,  # 26.0 k-VND
            }
        ]
        result = compute_evaluations(recs, prices, holdings=holdings)
        # eod_low=26.0 == stop=26.0 → breached (<=)
        assert result[0]["stop_hit"] is True
        assert result[0]["status"] == "STOP_BREACHED"


# ============================================================================
# Fix 1: N/A entry_hit_rate when no entry actions
# ============================================================================
