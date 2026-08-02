"""Tests for retro evaluator commentary validation."""

import pytest

from agents.retro.validate import (
    ValidationResult,
    Violation,
    validate_eval_commentary,
)

# ============================================================================
# Helpers
# ============================================================================


def _make_pre(ticker, **overrides):
    """Create a pre-computed eval dict with sensible defaults."""
    base = {
        "ticker": ticker,
        "recommendation": "BUY",
        "status": "PENDING",
        "entry_hit": True,
        "stop_hit": False,
        "target_hit": False,
        "eod_price": 35000,
        "pnl_percent": 1.5,
        "day_change": None,
        "direction_correct": True,
    }
    base.update(overrides)
    return base


def _make_analysis(ticker, **overrides):
    """Create a TickerAnalysis dict with sensible defaults."""
    base = {
        "ticker": ticker,
        "analysis": "Stock moved as expected.",
        "error_type": "N/A",
        "lesson": "",
    }
    base.update(overrides)
    return base


# ============================================================================
# Stop Fabrication
# ============================================================================


class TestStopFabrication:
    def test_flags_stop_triggered_when_stop_hit_false(self):
        pre = [_make_pre("VHM", stop_hit=False)]
        analyses = [_make_analysis("VHM", analysis="Stock stop triggered intraday at 93k.")]
        result = validate_eval_commentary(analyses, pre)
        assert not result.passed
        assert result.violations[0].check == "STOP_FABRICATION"
        assert result.violations[0].ticker == "VHM"

    def test_allows_stop_triggered_when_stop_hit_true(self):
        pre = [_make_pre("VHM", stop_hit=True)]
        analyses = [_make_analysis("VHM", analysis="Stop was hit at 93k, loss taken.")]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed

    @pytest.mark.parametrize(
        "phrase",
        [
            "stop was hit at the 93k level",
            "stopped out during afternoon session",
            "stop triggered by gap down",
            "hit the stop loss at 93k",
            "stop breach confirmed",
            "stop activated intraday",
        ],
    )
    def test_catches_variant_phrases(self, phrase):
        pre = [_make_pre("VHM", stop_hit=False)]
        analyses = [_make_analysis("VHM", analysis=phrase)]
        result = validate_eval_commentary(analyses, pre)
        assert not result.passed
        assert result.violations[0].check == "STOP_FABRICATION"

    def test_ignores_unrelated_text(self):
        pre = [_make_pre("VHM", stop_hit=False)]
        analyses = [_make_analysis("VHM", analysis="Price stayed above stop level all day.")]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed


# ============================================================================
# Error Type Consistency
# ============================================================================


class TestErrorTypeConsistency:
    def test_flags_analysis_error_when_direction_correct(self):
        pre = [_make_pre("TCB", direction_correct=True)]
        analyses = [_make_analysis("TCB", error_type="ANALYSIS_ERROR")]
        result = validate_eval_commentary(analyses, pre)
        assert not result.passed
        assert result.violations[0].check == "ERROR_TYPE_MISMATCH"

    def test_flags_variance_when_direction_wrong(self):
        pre = [_make_pre("TCB", direction_correct=False)]
        analyses = [_make_analysis("TCB", error_type="VARIANCE")]
        result = validate_eval_commentary(analyses, pre)
        assert not result.passed
        assert result.violations[0].check == "ERROR_TYPE_MISMATCH"

    def test_flags_execution_error_when_direction_wrong(self):
        pre = [_make_pre("TCB", direction_correct=False)]
        analyses = [_make_analysis("TCB", error_type="EXECUTION_ERROR")]
        result = validate_eval_commentary(analyses, pre)
        assert not result.passed

    def test_allows_analysis_error_when_direction_wrong(self):
        pre = [_make_pre("TCB", direction_correct=False)]
        analyses = [_make_analysis("TCB", error_type="ANALYSIS_ERROR")]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed

    def test_allows_execution_error_when_direction_correct(self):
        pre = [_make_pre("TCB", direction_correct=True)]
        analyses = [_make_analysis("TCB", error_type="EXECUTION_ERROR")]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed

    def test_skips_when_direction_none(self):
        pre = [_make_pre("TCB", direction_correct=None)]
        analyses = [_make_analysis("TCB", error_type="ANALYSIS_ERROR")]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed

    def test_skips_na_error_type(self):
        pre = [_make_pre("TCB", direction_correct=True)]
        analyses = [_make_analysis("TCB", error_type="N/A")]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed


# ============================================================================
# P/L Metric Misuse
# ============================================================================


class TestPnlMetricMisuse:
    def test_flags_pnl_in_trim_analysis(self):
        pre = [_make_pre("VHM", recommendation="TRIM", pnl_percent=7.3, day_change=-6.9)]
        analyses = [_make_analysis("VHM", analysis="Position still +7.3% from entry.")]
        result = validate_eval_commentary(analyses, pre)
        assert not result.passed
        assert result.violations[0].check == "PNL_METRIC_MISUSE"

    def test_flags_pnl_in_exit_analysis(self):
        pre = [_make_pre("FPT", recommendation="EXIT", pnl_percent=-6.3, day_change=-2.6)]
        analyses = [_make_analysis("FPT", analysis="Stock dropped 6.3% from entry.")]
        result = validate_eval_commentary(analyses, pre)
        assert not result.passed
        assert result.violations[0].check == "PNL_METRIC_MISUSE"

    def test_allows_day_change_citation(self):
        pre = [_make_pre("VHM", recommendation="TRIM", pnl_percent=7.3, day_change=-6.9)]
        analyses = [_make_analysis("VHM", analysis="Stock dropped 6.9% today.")]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed

    def test_allows_both_metrics(self):
        pre = [_make_pre("VHM", recommendation="TRIM", pnl_percent=7.3, day_change=-6.9)]
        analyses = [
            _make_analysis("VHM", analysis="Stock +7.3% from entry but dropped 6.9% today.")
        ]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed

    def test_skips_buy_actions(self):
        pre = [_make_pre("TCB", recommendation="BUY", pnl_percent=-3.0, day_change=-3.0)]
        analyses = [_make_analysis("TCB", analysis="Stock dropped 3.0% from entry.")]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed

    def test_skips_when_metrics_similar(self):
        pre = [_make_pre("VHM", recommendation="HOLD", pnl_percent=2.1, day_change=1.8)]
        analyses = [_make_analysis("VHM", analysis="Stock up 2.1% from entry.")]
        result = validate_eval_commentary(analyses, pre)
        # Difference < 1.0 → not flagged
        assert result.passed

    def test_skips_when_pnl_none(self):
        pre = [_make_pre("VHM", recommendation="HOLD", pnl_percent=None, day_change=-2.0)]
        analyses = [_make_analysis("VHM", analysis="No entry data available.")]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed

    def test_flags_counterfactual_without_day_change(self):
        # Today's TCB shape: LONGTERM HOLD, day_change=-1.1%, pnl_percent=-1.85%.
        # Narrative: "would have locked -0.8% vs EOD -1.9%" — counterfactual
        # language without citing day_change (1.1%).
        pre = [_make_pre("TCB", recommendation="HOLD", pnl_percent=-1.85, day_change=-1.1)]
        analyses = [
            _make_analysis(
                "TCB",
                analysis="Holding preserved capital vs exit at midday 31.95k which would have locked -0.8%.",
            )
        ]
        result = validate_eval_commentary(analyses, pre)
        assert not result.passed
        assert result.violations[0].check == "PNL_METRIC_MISUSE"
        assert "counterfactual" in result.violations[0].detail.lower()

    def test_allows_counterfactual_with_day_change(self):
        # Same shape, but narrative also cites day_change → valid.
        pre = [_make_pre("TCB", recommendation="HOLD", pnl_percent=-1.85, day_change=-1.1)]
        analyses = [
            _make_analysis(
                "TCB",
                analysis="Day_change=-1.1% within thesis-intact floor — would have locked -0.8% at midday.",
            )
        ]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed


# ============================================================================
# Duplicate Tickers
# ============================================================================


class TestDuplicateTickers:
    def test_flags_duplicate(self):
        pre = [_make_pre("VNM"), _make_pre("VNM")]
        analyses = [
            _make_analysis("VNM", analysis="Good call."),
            _make_analysis("VNM", analysis="Bad call."),
        ]
        result = validate_eval_commentary(analyses, pre)
        assert not result.passed
        assert result.violations[0].check == "DUPLICATE_TICKER"

    def test_allows_unique(self):
        pre = [_make_pre("VNM"), _make_pre("TCB")]
        analyses = [
            _make_analysis("VNM", analysis="Good."),
            _make_analysis("TCB", analysis="Good."),
        ]
        result = validate_eval_commentary(analyses, pre)
        assert result.passed


# ============================================================================
# ValidationResult
# ============================================================================


class TestValidationResult:
    def test_passed_when_no_violations(self):
        r = ValidationResult()
        assert r.passed

    def test_not_passed_with_violations(self):
        r = ValidationResult(
            violations=[Violation("VHM", "STOP_FABRICATION", "critical", "test", "fix")]
        )
        assert not r.passed

    def test_format_for_retry_empty_when_passed(self):
        r = ValidationResult()
        assert r.format_for_retry() == ""

    def test_counts_by_check_aggregates_violations(self):
        # Aggregated per-check counts for operator-facing summaries.
        r = ValidationResult(
            violations=[
                Violation("VHM", "PNL_METRIC_MISUSE", "major", "a", "x"),
                Violation("TCB", "PNL_METRIC_MISUSE", "major", "b", "y"),
                Violation("FPT", "STOP_FABRICATION", "critical", "c", "z"),
            ]
        )
        counts = r.counts_by_check()
        assert counts == {"PNL_METRIC_MISUSE": 2, "STOP_FABRICATION": 1}

    def test_counts_by_check_empty_when_no_violations(self):
        assert ValidationResult().counts_by_check() == {}

    def test_format_for_retry_includes_violations(self):
        r = ValidationResult(
            violations=[
                Violation("VHM", "STOP_FABRICATION", "critical", "bad claim", "remove it"),
                Violation("FPT", "PNL_METRIC_MISUSE", "major", "wrong metric", "use day_change"),
            ]
        )
        text = r.format_for_retry()
        assert "VALIDATION FAILURES" in text
        assert "[STOP_FABRICATION] VHM" in text
        assert "[PNL_METRIC_MISUSE] FPT" in text
        assert "Fix:" in text


# ============================================================================
# Integration: multiple violations in one pass
# ============================================================================


class TestMultipleViolations:
    def test_catches_all_issues_in_one_pass(self):
        pre = [
            _make_pre(
                "VHM", stop_hit=False, recommendation="TRIM", pnl_percent=7.3, day_change=-6.9
            ),
            _make_pre("FPT", direction_correct=True),
        ]
        analyses = [
            _make_analysis(
                "VHM",
                analysis="Stop triggered at 93k. Position still +7.3% from entry.",
            ),
            _make_analysis("FPT", error_type="ANALYSIS_ERROR"),
        ]
        result = validate_eval_commentary(analyses, pre)
        checks = {v.check for v in result.violations}
        assert "STOP_FABRICATION" in checks
        assert "PNL_METRIC_MISUSE" in checks
        assert "ERROR_TYPE_MISMATCH" in checks
