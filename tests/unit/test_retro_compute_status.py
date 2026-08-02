"""Tests for deterministic retrospective evaluation — status."""

import pytest

from agents.retro.compute import compute_day_summary, compute_evaluations
from agents.retro.mode import compute_mode_compliance
from agents.retro.won import compute_won

pytestmark = pytest.mark.usefixtures("mock_trading_config")


class TestPendingStatus:
    """Entry hit but neither stop nor target hit → PENDING."""

    def test_pending_positive(self, eod_prices):
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
        # Entry hit, stop not hit, target not hit → PENDING
        assert result[0]["status"] == "PENDING"

    def test_pending_not_scoreable(self, eod_prices):
        """PENDING evaluations should have won=None (not scoreable, not a loss)."""
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
        assert result[0]["status"] == "PENDING"
        assert result[0]["won"] is None  # not False

    def test_pending_excluded_from_win_rate(self, eod_prices):
        """PENDING evals must not inflate win_rate denominator."""
        prices = {
            "VHM": {"open": 95.0, "high": 101.0, "low": 94.5, "close": 100.7, "volume": 8000000},
            "HDB": {"open": 27.0, "high": 27.5, "low": 26.5, "close": 27.2, "volume": 5000000},
        }
        recs = [
            {
                "ticker": "VHM",
                "action": "BUY",
                "entry_price": 95000,
                "stop_price": 93000,
                "target_price": 101000,
            },  # WIN (target hit)
            {
                "ticker": "HDB",
                "action": "BUY",
                "entry_price": 26800,
                "stop_price": 26200,
                "target_price": 30000,
            },  # PENDING (entry hit, no target/stop)
        ]
        evals = compute_evaluations(recs, prices)
        summary = compute_day_summary(evals)
        # Only VHM counts; HDB PENDING excluded
        assert summary["total_recs"] == 1
        assert summary["win_rate"] == 100.0


# ============================================================================
# compute_evaluations: SKIP/AVOID/WAIT/WATCH → EXCLUDED
# ============================================================================


class TestModeCompliance:
    def test_normal_no_violations(self):
        recs = [{"ticker": "TCB", "action": "BUY"}]
        ok, violations = compute_mode_compliance(recs, "NORMAL")
        assert ok is True
        assert violations == []

    def test_low_cash_buy_violation(self):
        recs = [{"ticker": "TCB", "action": "BUY"}]
        ok, violations = compute_mode_compliance(recs, "LOW_CASH")
        assert ok is False
        assert len(violations) == 1
        assert "BUY" in violations[0]

    def test_low_cash_hold_ok(self):
        recs = [{"ticker": "TCB", "action": "HOLD"}]
        ok, violations = compute_mode_compliance(recs, "LOW_CASH")
        assert ok is True

    def test_reallocation_needs_exit(self):
        recs = [{"ticker": "TCB", "action": "HOLD"}]
        ok, violations = compute_mode_compliance(recs, "REALLOCATION")
        assert ok is False
        assert any("No EXIT" in v for v in violations)

    def test_reallocation_with_exit(self):
        recs = [
            {"ticker": "TCB", "action": "EXIT"},
            {"ticker": "VHM", "action": "HOLD"},
        ]
        ok, violations = compute_mode_compliance(recs, "REALLOCATION")
        assert ok is True

    def test_na_mode(self):
        recs = [{"ticker": "TCB", "action": "BUY"}]
        ok, violations = compute_mode_compliance(recs, "N/A")
        assert ok is True


# ============================================================================
# MISSED rate warning
# ============================================================================


class TestMissedRateWarning:
    """compute_evaluations warns when >30% of evaluations are MISSED."""

    def test_high_missed_rate_logs_warning(self, caplog):
        """4/5 MISSED (80%) should trigger warning."""
        import logging

        recs = [
            {"ticker": "A1", "action": "BUY", "entry_price": 50000},
            {"ticker": "A2", "action": "BUY", "entry_price": 50000},
            {"ticker": "A3", "action": "BUY", "entry_price": 50000},
            {"ticker": "A4", "action": "BUY", "entry_price": 50000},
            {
                "ticker": "TCB",
                "action": "BUY",
                "entry_price": 34800,
                "stop_price": 33000,
                "target_price": 38000,
            },
        ]
        prices = {
            "TCB": {"open": 34.85, "high": 35.9, "low": 34.8, "close": 35.9, "volume": 11603200},
        }
        with caplog.at_level(logging.WARNING):
            evals = compute_evaluations(recs, prices)

        missed = [e for e in evals if e["status"] == "MISSED"]
        assert len(missed) == 4
        assert "High MISSED rate" in caplog.text
        assert "80%" in caplog.text

    def test_low_missed_rate_no_warning(self, eod_prices, caplog):
        """1/5 MISSED (20%) should NOT trigger warning."""
        import logging

        recs = [
            {"ticker": "UNKNOWN", "action": "BUY", "entry_price": 50000},
            {
                "ticker": "TCB",
                "action": "BUY",
                "entry_price": 34800,
                "stop_price": 33000,
                "target_price": 38000,
            },
            {
                "ticker": "HDB",
                "action": "BUY",
                "entry_price": 26800,
                "stop_price": 26200,
                "target_price": 30000,
            },
            {"ticker": "VHM", "action": "HOLD"},
            {"ticker": "GAS", "action": "WATCH"},
        ]
        with caplog.at_level(logging.WARNING):
            compute_evaluations(recs, eod_prices)

        assert "High MISSED rate" not in caplog.text

    def test_missed_for_missing_price(self):
        """Ticker with no price data -> MISSED."""
        recs = [{"ticker": "NODATA", "action": "BUY", "entry_price": 50000}]
        evals = compute_evaluations(recs, {})
        assert evals[0]["status"] == "MISSED"

    def test_missed_for_zero_close(self):
        """Ticker with close=0 -> MISSED."""
        prices = {"TCB": {"open": 0, "high": 0, "low": 0, "close": 0}}
        recs = [{"ticker": "TCB", "action": "BUY", "entry_price": 34000}]
        evals = compute_evaluations(recs, prices)
        assert evals[0]["status"] == "MISSED"


# ============================================================================
# HOLD stop breach detection (Fix 1a)
# ============================================================================


class TestEntryHitRateNone:
    """entry_hit_rate should be None when no BUY/ADD/LIMIT_BUY recommendations."""

    def test_no_entry_recs_returns_none(self):
        """Only HOLD recs → entry_hit_rate is None, not 0.0."""
        evals = [
            {
                "ticker": "FPT",
                "recommendation": "HOLD",
                "status": "HOLD",
                "entry_hit": False,
                "has_entry_data": True,
                "won": True,
                "pnl_percent": -0.5,
                "day_change": -0.5,
            }
        ]
        summary = compute_day_summary(evals)
        assert summary["entry_hit_rate"] is None
        assert summary["win_rate"] == 100.0  # HOLD still counted in win_rate

    def test_empty_evals_returns_none(self):
        summary = compute_day_summary([])
        assert summary["entry_hit_rate"] is None

    def test_all_excluded_returns_none(self, eod_prices):
        recs = [
            {"ticker": "GAS", "action": "AVOID"},
            {"ticker": "VHM", "action": "SKIP"},
        ]
        evals = compute_evaluations(recs, eod_prices)
        summary = compute_day_summary(evals)
        assert summary["entry_hit_rate"] is None

    def test_with_entry_recs_returns_number(self, eod_prices, buy_recs):
        evals = compute_evaluations(buy_recs, eod_prices)
        summary = compute_day_summary(evals)
        assert summary["entry_hit_rate"] is not None
        assert isinstance(summary["entry_hit_rate"], float)


# ============================================================================
# Fix 2: Configurable HOLD loss threshold
# ============================================================================


class TestComputeWonThreshold:
    """compute_won() respects hold_loss_threshold_pct parameter."""

    def test_default_threshold_wins_at_minus_1_5(self):
        """day_change=-1.5% wins at default threshold (2.0%)."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": -1.5}
        assert compute_won(evaluation) is True

    def test_default_threshold_loses_at_minus_2_5(self):
        """day_change=-2.5% loses at default threshold (2.0%)."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": -2.5}
        assert compute_won(evaluation) is False

    def test_exact_boundary_wins(self):
        """day_change exactly at -threshold is a win (>=)."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": -2.0}
        assert compute_won(evaluation, hold_loss_threshold_pct=2.0) is True

    def test_custom_threshold_1_0(self):
        """Custom threshold: day_change=-1.5% loses at 1.0% threshold."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": -1.5}
        assert compute_won(evaluation, hold_loss_threshold_pct=1.0) is False

    def test_custom_threshold_3_0(self):
        """Custom threshold: day_change=-2.5% wins at 3.0% threshold."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": -2.5}
        assert compute_won(evaluation, hold_loss_threshold_pct=3.0) is True

    def test_trim_exit_threshold_unaffected(self):
        """TRIM/EXIT held uses day_change >= 0, unaffected by hold threshold."""
        evaluation = {"status": "HOLD", "recommendation": "TRIM", "day_change": -0.5}
        # TRIM held: win if stock didn't drop at all (>= 0)
        assert compute_won(evaluation, hold_loss_threshold_pct=5.0) is False

    def test_non_hold_statuses_unaffected(self):
        """WIN/LOSS/EXCLUDED unaffected by threshold."""
        assert compute_won({"status": "WIN", "recommendation": "BUY"}) is True
        assert compute_won({"status": "EXCLUDED", "recommendation": "SKIP"}) is None
        assert compute_won({"status": "LOSS", "recommendation": "BUY"}) is False


class TestComputeWonPlanType:
    """Tests for plan_type-aware HOLD win logic."""

    def test_swing_hold_flat_day_is_not_win(self):
        """SWING HOLD at 0.0% day_change → won=False (strict positive)."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": 0.0}
        assert compute_won(evaluation, plan_type="SWING") is False

    def test_swing_hold_positive_day_is_win(self):
        """SWING HOLD at +0.1% → won=True."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": 0.1}
        assert compute_won(evaluation, plan_type="SWING") is True

    def test_swing_hold_negative_day_is_loss(self):
        """SWING HOLD at -1.5% → won=False."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": -1.5}
        assert compute_won(evaluation, plan_type="SWING") is False

    def test_longterm_hold_within_threshold_is_win(self):
        """LONGTERM HOLD at -1.5% (within -2% threshold) → won=True."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": -1.5}
        assert compute_won(evaluation, plan_type="LONGTERM") is True

    def test_longterm_hold_exceeds_threshold_is_loss(self):
        """LONGTERM HOLD at -2.5% (exceeds -2%) → won=False."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": -2.5}
        assert compute_won(evaluation, plan_type="LONGTERM") is False

    def test_longterm_hold_flat_day_is_win(self):
        """LONGTERM HOLD at 0.0% → won=True (within threshold)."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": 0.0}
        assert compute_won(evaluation, plan_type="LONGTERM") is True

    def test_none_plan_type_uses_threshold_fallback(self):
        """Unknown plan_type falls back to threshold-based (conservative)."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": -1.5}
        assert compute_won(evaluation, plan_type=None) is True

    def test_none_plan_type_exceeds_threshold(self):
        """Unknown plan_type at -2.5% → won=False."""
        evaluation = {"status": "HOLD", "recommendation": "HOLD", "day_change": -2.5}
        assert compute_won(evaluation, plan_type=None) is False

    def test_trim_exit_unaffected_by_plan_type(self):
        """TRIM/EXIT always uses day_change >= 0, regardless of plan_type."""
        evaluation = {"status": "HOLD", "recommendation": "TRIM", "day_change": -0.5}
        assert compute_won(evaluation, plan_type="LONGTERM") is False
        assert compute_won(evaluation, plan_type="SWING") is False

    def test_executed_trade_unaffected_by_plan_type(self):
        """Executed trades use actual_pl_pct, not plan_type logic."""
        evaluation = {
            "status": "HOLD",
            "recommendation": "HOLD",
            "trade_executed": True,
            "actual_pl_pct": -5.0,
        }
        assert compute_won(evaluation, plan_type="LONGTERM") is False
        assert compute_won(evaluation, plan_type="SWING") is False
