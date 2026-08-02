#!/usr/bin/env python3
"""
Deterministic validation of LLM EvaluationCommentary against pre-computed data.

Catches fabrications the LLM makes that contradict compute.py results.
Pure Python — no DB, no LLM, no async.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from shared.narrative import _EXECUTION_PHRASES, narrative_truth_check

# Actions evaluated by day_change, not pnl_percent
_HOLD_ACTIONS = {"HOLD", "EXIT", "TRIM"}

# Phrases indicating a stop was triggered
_STOP_PHRASES = re.compile(
    r"stop\s*(was\s+)?(?:hit|triggered|breach|broken|activated)"
    r"|stopped?\s+out"
    r"|hit\s+(the\s+)?stop",
    re.IGNORECASE,
)

# Phrases indicating entry was triggered
_ENTRY_HIT_PHRASES = re.compile(
    r"entry\s*(was\s+)?(?:hit|triggered|filled|reached)"
    r"|entered\s+at"
    r"|position\s+opened"
    r"|filled\s+at"
    r"|limit\s+(?:buy\s+)?filled",
    re.IGNORECASE,
)

# Counterfactual phrases that typically mix running pnl with daily movement
# when writing HOLD/TRIM/EXIT commentary.
_COUNTERFACTUAL_PHRASES = re.compile(
    r"would\s+have\s+(locked|saved|avoided|captured|returned|been)"
    r"|if\s+exited"
    r"|if\s+we\s+(had\s+)?(?:exited|sold|closed)"
    r"|counterfactual",
    re.IGNORECASE,
)


@dataclass
class Violation:
    ticker: str
    check: str  # STOP_FABRICATION, PNL_METRIC_MISUSE, ERROR_TYPE_MISMATCH, DUPLICATE_TICKER
    severity: str  # critical, major
    detail: str
    suggestion: str


@dataclass
class ValidationResult:
    violations: list[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0

    def counts_by_check(self) -> dict[str, int]:
        """Aggregate violations by check type for operator-facing summaries."""
        return dict(Counter(v.check for v in self.violations))

    def format_for_retry(self) -> str:
        """Format violations as critique text for evaluator retry."""
        if self.passed:
            return ""
        lines = ["VALIDATION FAILURES (your previous output contradicted pre-computed data):"]
        for v in self.violations:
            lines.append(f"- [{v.check}] {v.ticker}: {v.detail} Fix: {v.suggestion}")
        return "\n".join(lines)


def validate_eval_commentary(
    commentary_analyses: list[dict],
    pre_evals: list[dict],
) -> ValidationResult:
    """Validate LLM commentary against pre-computed evaluation data.

    Args:
        commentary_analyses: List of TickerAnalysis dicts from LLM
        pre_evals: List of evaluation dicts from compute_evaluations()

    Returns:
        ValidationResult with any violations found.
    """
    result = ValidationResult()
    pre_map = {e["ticker"]: e for e in pre_evals}

    for analysis in commentary_analyses:
        ticker = analysis.get("ticker", "")
        pre = pre_map.get(ticker)
        if not pre:
            continue

        _check_stop_fabrication(analysis, pre, result)
        _check_entry_fabrication(analysis, pre, result)
        _check_execution_fabrication(analysis, pre, result)
        _check_error_type_consistency(analysis, pre, result)
        _check_pnl_metric_misuse(analysis, pre, result)

    _check_duplicate_tickers(commentary_analyses, result)

    return result


def _check_stop_fabrication(
    analysis: dict,
    pre: dict,
    result: ValidationResult,
) -> None:
    """Flag when LLM claims stop triggered but pre-computed stop_hit=False."""
    violation = narrative_truth_check(
        analysis.get("analysis") or "",
        phrases=_STOP_PHRASES,
        structural_value=bool(pre.get("stop_hit")),
        expected=True,
        check_name="STOP_FABRICATION",
        severity="critical",
        detail="Analysis claims stop triggered but pre-computed stop_hit=False",
        suggestion="Remove stop trigger claim from analysis text.",
    )
    if violation:
        result.violations.append(
            Violation(
                ticker=pre["ticker"],
                check=violation.check,
                severity=violation.severity,
                detail=violation.detail,
                suggestion=violation.suggestion,
            )
        )


def _check_entry_fabrication(
    analysis: dict,
    pre: dict,
    result: ValidationResult,
) -> None:
    """Flag when LLM claims entry hit but pre-computed entry_hit=False."""
    status = pre.get("status", "")
    if status in ("EXCLUDED", "HOLD"):
        return  # not an entry trade

    violation = narrative_truth_check(
        analysis.get("analysis") or "",
        phrases=_ENTRY_HIT_PHRASES,
        structural_value=bool(pre.get("entry_hit")),
        expected=True,
        check_name="ENTRY_FABRICATION",
        severity="critical",
        detail=f"Analysis claims entry hit but pre-computed entry_hit=False (status: {status})",
        suggestion=f"Remove entry hit claim. Status is {status}.",
    )
    if violation:
        result.violations.append(
            Violation(
                ticker=pre["ticker"],
                check=violation.check,
                severity=violation.severity,
                detail=violation.detail,
                suggestion=violation.suggestion,
            )
        )


def _check_execution_fabrication(
    analysis: dict,
    pre: dict,
    result: ValidationResult,
) -> None:
    """Flag when LLM narrative implies the trade closed but trade_executed=False.

    Root of SWI-255 — midday-emitted "position closed per stop-loss
    discipline" reason text was being read by retro_commentary as an
    execution fact and mirrored into ``daily_evaluations.analysis``.
    """
    violation = narrative_truth_check(
        analysis.get("analysis") or "",
        phrases=_EXECUTION_PHRASES,
        structural_value=bool(pre.get("trade_executed")),
        expected=True,
        check_name="EXECUTION_FABRICATION",
        severity="critical",
        detail=(
            "Analysis uses outcome verbs (executed/closed/taken/stopped out) "
            "but pre-computed trade_executed=False — no closed_trades row exists."
        ),
        suggestion=(
            "Use signal language: 'signal cancelled', 'intraday touched stop and bounced', "
            "'would have stopped at X'. Outcome verbs belong only in the EXECUTED prefix."
        ),
    )
    if violation:
        result.violations.append(
            Violation(
                ticker=pre["ticker"],
                check=violation.check,
                severity=violation.severity,
                detail=violation.detail,
                suggestion=violation.suggestion,
            )
        )


def _check_error_type_consistency(
    analysis: dict,
    pre: dict,
    result: ValidationResult,
) -> None:
    """Cross-check error_type against direction_correct hint."""
    error_type = analysis.get("error_type", "N/A")
    direction = pre.get("direction_correct")

    if direction is None:
        return  # no direction data (e.g., MISSED, EXCLUDED)

    if direction is True and error_type == "ANALYSIS_ERROR":
        result.violations.append(
            Violation(
                ticker=pre["ticker"],
                check="ERROR_TYPE_MISMATCH",
                severity="major",
                detail=(
                    "error_type=ANALYSIS_ERROR but direction_correct=True. "
                    "Direction was right, so thesis wasn't fundamentally wrong."
                ),
                suggestion="Use EXECUTION_ERROR or VARIANCE instead of ANALYSIS_ERROR.",
            )
        )
    elif direction is False and error_type in ("EXECUTION_ERROR", "VARIANCE"):
        result.violations.append(
            Violation(
                ticker=pre["ticker"],
                check="ERROR_TYPE_MISMATCH",
                severity="major",
                detail=(
                    f"error_type={error_type} but direction_correct=False. "
                    "Direction was wrong — this is an analysis failure."
                ),
                suggestion="Use ANALYSIS_ERROR when direction was wrong.",
            )
        )


def _check_pnl_metric_misuse(
    analysis: dict,
    pre: dict,
    result: ValidationResult,
) -> None:
    """Flag HOLD/EXIT/TRIM analyses citing pnl_percent instead of day_change."""
    action = (pre.get("recommendation") or "").upper()
    if action not in _HOLD_ACTIONS:
        return

    pnl = pre.get("pnl_percent")
    day = pre.get("day_change")
    if pnl is None or day is None:
        return

    text = analysis.get("analysis") or ""
    pnl_str = f"{abs(pnl):.1f}%"
    day_str = f"{abs(day):.1f}%"

    has_pnl = pnl_str in text
    has_day = day_str in text
    has_counterfactual = bool(_COUNTERFACTUAL_PHRASES.search(text))
    metrics_differ = abs(pnl - day) >= 1.0

    # Counterfactual phrasing is flagged independent of value skew because
    # the narrative itself conflates running P/L with daily movement
    # (see 2026-04-13 TCB review).
    pattern_1 = has_pnl and not has_day and metrics_differ
    pattern_2 = has_counterfactual and not has_day
    if not (pattern_1 or pattern_2):
        return

    reason = (
        "counterfactual phrasing without day_change citation"
        if pattern_2 and not pattern_1
        else "pnl cited without day_change"
    )
    result.violations.append(
        Violation(
            ticker=pre["ticker"],
            check="PNL_METRIC_MISUSE",
            severity="major",
            detail=(
                f"{action} analysis — {reason}: pnl_percent={pnl:+.1f}%, "
                f"day_change={day:+.1f}%. HOLD rows are scored by day_change."
            ),
            suggestion=f"Use day_change={day:+.1f}% for {action} accuracy, not P/L from entry.",
        )
    )


def _check_duplicate_tickers(
    analyses: list[dict],
    result: ValidationResult,
) -> None:
    """Flag any ticker appearing more than once in the analyses."""
    seen: dict[str, int] = {}
    for a in analyses:
        ticker = a.get("ticker", "")
        seen[ticker] = seen.get(ticker, 0) + 1

    for ticker, count in seen.items():
        if count > 1:
            result.violations.append(
                Violation(
                    ticker=ticker,
                    check="DUPLICATE_TICKER",
                    severity="major",
                    detail=f"Ticker appears {count} times in analyses (should be unique).",
                    suggestion="Consolidate into a single analysis entry per ticker.",
                )
            )
