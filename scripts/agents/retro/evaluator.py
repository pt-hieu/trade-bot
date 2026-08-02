#!/usr/bin/env python3
"""
Day Evaluator — deterministic calculations + LLM commentary + validation.

Numeric fields (entry_hit, stop_hit, target_hit, pnl_percent, status)
are computed in Python via compute.py. LLM only generates analysis text.

Flow:
1. Pre-compute evaluations, summary, compliance in Python
2. Ask LLM for analysis text per ticker + key_insight + midday summary
3. Merge LLM commentary into pre-computed evaluations
3.5. Validate commentary against pre-computed data; retry once if violations
3.6. LLM critic audit (non-blocking, logged only)
4. Compute mode counterfactual
"""

import logging
from datetime import date

from pydantic import BaseModel

from shared.errors import report_caught
from shared.neon import ClosedTradeEntry

logger = logging.getLogger(__name__)

from shared.rules.retro_rule_classifier import classify_retro_rule
from shared.trading_config import get_trading_config

from .commentary import (
    EvaluationCommentary,
    MiddaySummary,
    TickerAnalysis,
    get_llm_commentary,
)
from .compute import compute_day_summary, compute_evaluations
from .mode import compute_mode_compliance, compute_mode_counterfactual
from .render import build_deterministic_prefixes_block, stamp_deterministic_prefix
from .validate import validate_eval_commentary

__all__ = [
    "EvaluationCommentary",
    "MiddaySummary",
    "TickerAnalysis",
    "build_deterministic_prefixes_block",
]

# ============================================================================
# Pydantic models (backward-compatible output structure)
# ============================================================================


class Evaluation(BaseModel):
    """Evaluation of a single recommendation."""

    ticker: str
    recommendation: str
    entry_hit: bool
    stop_hit: bool
    target_hit: bool
    eod_price: float
    pnl_percent: float | None = None
    day_change: float | None = None
    has_entry_data: bool | None = None
    status: str  # WIN, LOSS, PENDING, MISSED, HOLD, EXCLUDED
    analysis: str


class DaySummary(BaseModel):
    """Summary of the day's recommendations."""

    total_recs: int
    entry_hit_rate: float | None = None
    win_rate: float
    best_call: str
    worst_call: str
    key_insight: str


class DayEvaluation(BaseModel):
    """Complete day evaluation result."""

    evaluations: list[Evaluation]
    midday_evaluations: list[Evaluation]
    day_summary: DaySummary
    midday_summary: MiddaySummary | None
    adjustment_effectiveness: str
    trading_mode: str
    mode_compliance: bool
    mode_violations: list[str]


# ============================================================================
# Main evaluation function
# ============================================================================


def _empty_result(
    recommendations: list[dict],
    midday_data: dict | None,
) -> dict:
    """Return empty result when no recs to evaluate."""
    return {
        "evaluations": [],
        "midday_evaluations": [],
        "day_summary": {
            "total_recs": 0,
            "entry_hit_rate": 0.0,
            "win_rate": 0.0,
            "best_call": "None",
            "worst_call": "None",
            "key_insight": "No recommendations to evaluate",
        },
        "midday_summary": None,
        "adjustment_effectiveness": "N/A",
        "trading_mode": (midday_data.get("trading_mode") or "NORMAL") if midday_data else "NORMAL",
        "mode_compliance": True,
        "mode_violations": [],
    }


def _merge_commentary(
    pre_evals: list[dict],
    pre_summary: dict,
    commentary: EvaluationCommentary,
) -> tuple[dict | None, str]:
    """Merge LLM commentary into pre-computed evals. Returns (midday_summary, adjustment_eff)."""
    analysis_map = {a.ticker: (a.analysis, a.error_type, a.lesson) for a in commentary.analyses}
    for e in pre_evals:
        if e["ticker"] in analysis_map:
            text, err_type, lesson = analysis_map[e["ticker"]]
            e["analysis"] = stamp_deterministic_prefix(e, text)
            e["error_type"] = err_type
            e["lesson"] = lesson
        else:
            e["analysis"] = stamp_deterministic_prefix(e, e.get("analysis") or "")
    pre_summary["key_insight"] = commentary.key_insight
    midday_summary = commentary.midday_summary.model_dump() if commentary.midday_summary else None
    return midday_summary, commentary.adjustment_effectiveness


async def evaluate_day_with_agent(
    recommendations: list[dict],
    eod_prices: dict | None = None,
    scan_date: date | None = None,
    midday_data: dict | None = None,
    holdings: list | None = None,
    closed_trades: list[ClosedTradeEntry] | None = None,
) -> dict:
    """Evaluate day's recommendations: deterministic numbers + LLM commentary."""
    if not recommendations:
        # Retry-path safety: empty recommendations is only legitimate when
        # the morning brief actually produced zero rows for this day. If
        # the DB shows morning recs > 0, we got here via a stale/missing
        # load — fail loud rather than silently writing zero evaluations.
        if scan_date is not None:
            try:
                from shared.neon.insert_records import get_morning_recommendations

                db_recs = await get_morning_recommendations(scan_date)
                if db_recs:
                    raise RuntimeError(
                        f"RETRO_EMPTY_RECS_ON_RETRY scan_date={scan_date} "
                        f"db_count={len(db_recs)} — evaluator received empty "
                        f"recommendations list but morning brief persisted "
                        f"{len(db_recs)} rows. Refusing to silently mark the "
                        f"day un-evaluated."
                    )
            except RuntimeError:
                raise
            except Exception as e:
                # Don't mask the original empty-list situation just because
                # the DB lookup failed — log + continue to the empty result.
                logger.warning("RETRO_EMPTY_RECS guard skipped (DB lookup failed): %s", e)
        return _empty_result(recommendations, midday_data)

    if scan_date is None:
        scan_date = date.today()

    prices = eod_prices or {}

    # Step 1: Deterministic computation
    pre_evals = compute_evaluations(
        recommendations, prices, holdings=holdings, closed_trades=closed_trades
    )
    pre_summary = compute_day_summary(pre_evals)

    longterm_catastrophic_pct = get_trading_config().longterm_catastrophic_pct
    for evaluation in pre_evals:
        evaluation["rule_applied"] = classify_retro_rule(
            evaluation,
            longterm_catastrophic_pct=longterm_catastrophic_pct,
        )

    mode = (midday_data.get("trading_mode") or "NORMAL") if midday_data else "NORMAL"
    compliance, violations = compute_mode_compliance(recommendations, mode)

    # Step 2: Ask LLM for qualitative commentary
    commentary = await get_llm_commentary(pre_evals, pre_summary, scan_date, midday_data)

    # Step 3: Merge LLM commentary into pre-computed evals
    midday_summary = None
    adjustment_eff = "N/A"
    validation_summary: dict[str, int] = {}

    quarantined_draft: str | None = None
    quarantine_violations: list[str] = []

    if commentary:
        midday_summary, adjustment_eff = _merge_commentary(pre_evals, pre_summary, commentary)

        # Step 3.5: Validate commentary against pre-computed data
        analyses_dicts = [a.model_dump() for a in commentary.analyses]
        validation = validate_eval_commentary(analyses_dicts, pre_evals)
        final_validation = validation

        if not validation.passed:
            critique = validation.format_for_retry()
            print(f"    Validation failed ({len(validation.violations)} issues), retrying...")
            for v in validation.violations:
                print(f"      [{v.check}] {v.ticker}: {v.detail}")

            # Retry with critique context
            retry_commentary = await get_llm_commentary(
                pre_evals, pre_summary, scan_date, midday_data, critique=critique
            )

            if retry_commentary:
                # Re-merge with retry output
                midday_summary, adjustment_eff = _merge_commentary(
                    pre_evals, pre_summary, retry_commentary
                )

                # Validate again (log-only, no more retries)
                retry_dicts = [a.model_dump() for a in retry_commentary.analyses]
                final_validation = validate_eval_commentary(retry_dicts, pre_evals)
                if not final_validation.passed:
                    print(f"    Retry still has {len(final_validation.violations)} violations")
                    for v in final_validation.violations:
                        print(f"      [{v.check}] {v.ticker}: {v.detail}")
                    # Quarantine when ANY critical violation persists after retry.
                    # Fail-loud recovery (SWI-255): preserve deterministic
                    # truth + violation list, reject the LLM draft.
                    has_critical = any(
                        v.severity == "critical" for v in final_validation.violations
                    )
                    if has_critical:
                        quarantined_draft = "\n\n".join(
                            f"### {a.get('ticker')}\n{a.get('analysis', '')}" for a in retry_dicts
                        )
                        quarantine_violations = [
                            f"[{v.check}] {v.ticker}: {v.detail}"
                            for v in final_validation.violations
                        ]
                else:
                    print("    Retry passed validation")

        # Surface warning-only accepted counts so operators can see repeats
        # accumulating across runs without us silently upgrading severity.
        validation_summary = final_validation.counts_by_check()
        if validation_summary:
            summary_str = ", ".join(
                f"{check}={count}" for check, count in sorted(validation_summary.items())
            )
            print(f"    Validation accepted counts: {summary_str}")

        # Step 3.6: LLM critic audit (non-blocking for transient infra,
        # fail-loud for contract violations — see eval_critic.py docstring).
        await _run_critic_audit(pre_evals, commentary, scan_date, midday_data)
    else:
        for e in pre_evals:
            e.setdefault("error_type", "N/A")
            e.setdefault("lesson", "")
            e["analysis"] = stamp_deterministic_prefix(e, e.get("analysis") or "")
            if e.get("status") == "PENDING":
                logger.warning("Commentary failed for %s — status remains PENDING", e.get("ticker"))

        # Fail-closed default (Python/LLM split): retro_commentary returned
        # nothing, so _merge_commentary never ran and key_insight would ship
        # the "" default from compute_day_summary (daily.py expects a
        # non-empty str). Substitute a deterministic one-liner — assigned
        # ONCE after the loop, never per-eval. Containment only (SWI-138).
        # best_call/worst_call carry the literal string "None" on a zero-PnL
        # day — treat that sentinel as "n/a".
        best_call = pre_summary.get("best_call")
        best_call = "n/a" if best_call in (None, "None") else best_call
        worst_call = pre_summary.get("worst_call")
        worst_call = "n/a" if worst_call in (None, "None") else worst_call
        pre_summary["key_insight"] = (
            f"{pre_summary.get('win_rate', 0):.0f}% win rate on "
            f"{pre_summary.get('total_recs', 0)} recs; best {best_call}, "
            f"worst {worst_call} (LLM commentary unavailable)."
        )
        logger.warning(
            "retro_commentary unavailable for %s — substituting deterministic key_insight",
            scan_date,
        )

    # Step 4: Compute mode counterfactual
    mode_counterfactual = compute_mode_counterfactual(pre_evals, mode, prices)

    print(f"    Evaluated {len(pre_evals)} recs: {pre_summary['win_rate']:.1f}% win rate")
    if midday_data:
        print(f"    Mode compliance: {compliance}, violations: {len(violations)}")

    return {
        "evaluations": pre_evals,
        "midday_evaluations": [],
        "day_summary": pre_summary,
        "midday_summary": midday_summary,
        "adjustment_effectiveness": adjustment_eff,
        "trading_mode": mode,
        "mode_compliance": compliance,
        "mode_violations": violations,
        "mode_counterfactual": mode_counterfactual,
        "validation_summary": validation_summary,
        "quarantined_draft": quarantined_draft,
        "quarantine_violations": quarantine_violations,
    }


async def _run_critic_audit(
    pre_evals: list[dict],
    commentary: EvaluationCommentary,
    scan_date: date,
    midday_data: dict | None,
) -> None:
    """Run LLM critic on evaluation commentary.

    Contract-failure propagation (SWI-141 / Fix 4):
        ``RetroEvalCriticContractFailure`` propagates to the retro pipeline
        entrypoint so the run aborts with non-zero exit. Transient infra
        failures inside ``critique_eval_commentary`` are absorbed there
        and return a no-issues stub (log-only). The outer
        ``report_caught`` wrapper here intentionally does NOT catch
        contract failures.
    """
    from .eval_critic import RetroEvalCriticContractFailure, critique_eval_commentary

    try:
        analyses_dicts = [a.model_dump() for a in commentary.analyses]
        result = await critique_eval_commentary(
            analyses_dicts, pre_evals, scan_date, midday_data=midday_data
        )
        if result.has_issues:
            print(f"    Eval critic found issues (severity={result.severity}): {result.summary}")
            for issue in result.issues:
                print(f"      - {issue}")
        else:
            print("    Eval critic: no issues")
    except RetroEvalCriticContractFailure:
        # Contract failure must propagate — not a transient infra issue.
        raise
    except Exception as e:
        report_caught("retro.evaluator.eval_critic", e)
