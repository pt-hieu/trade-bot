#!/usr/bin/env python3
"""
LLM commentary generation for retro evaluations.

Extracted from evaluator.py to keep files under 300 lines.
Contains LLM output models, prompt construction, agent creation, and retry-with-critique.
"""

import asyncio
import logging
from datetime import date
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent

from midday.formatter import format_afternoon_plan_prose
from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config
from shared.text_utils import format_kvnd

from ..agent_factory import AgentDeps, create_agent

logger = logging.getLogger(__name__)

# ============================================================================
# LLM output models (live here to avoid circular imports)
# ============================================================================


class MiddaySummary(BaseModel):
    """Summary of midday adjustments vs outcomes."""

    adjustments_made: int
    adjustments_helpful: int
    adjustments_harmful: int
    afternoon_accuracy: float
    key_adjustment: str


class TickerAnalysis(BaseModel):
    """LLM-generated commentary for a single evaluation."""

    ticker: str
    analysis: str
    error_type: Literal[
        "ANALYSIS_ERROR", "EXECUTION_ERROR", "CALIBRATION_ERROR", "VARIANCE", "N/A"
    ] = "N/A"
    lesson: str = ""


class EvaluationCommentary(BaseModel):
    """LLM output: qualitative fields only. Numbers are pre-computed."""

    analyses: list[TickerAnalysis]
    key_insight: str
    midday_summary: MiddaySummary | None = None
    adjustment_effectiveness: str = "N/A"


# ============================================================================
# Agent creation
# ============================================================================


async def create_commentary_agent() -> tuple[Agent[AgentDeps, EvaluationCommentary], AgentConfig]:
    """Create an agent that generates commentary on pre-computed evaluations."""
    config = await load_agent_config("retro_commentary")
    # HOOK-ALLOW: no-tickers-scope (retro commentary on pre-computed evaluations)
    agent = create_agent(config, output_type=EvaluationCommentary)
    return agent, config


# ============================================================================
# Commentary generation
# ============================================================================


async def get_llm_commentary(
    evaluations: list[dict],
    summary: dict,
    scan_date: date,
    midday_data: dict | None,
    critique: str | None = None,
) -> EvaluationCommentary | None:
    """Ask LLM for qualitative analysis of pre-computed evaluations.

    Args:
        evaluations: Pre-computed evaluation dicts from compute_evaluations()
        summary: Pre-computed day summary dict
        scan_date: Date being evaluated
        midday_data: Optional midday check data
        critique: Optional validation critique from a failed previous attempt.
                  When provided, appended to prompt so LLM can fix issues.

    Returns:
        EvaluationCommentary or None on failure.
    """
    evals_text = format_evals_for_llm(evaluations)
    entry_hit_rate = summary.get("entry_hit_rate")
    entry_hit_rate_str = f"{entry_hit_rate:.1f}%" if entry_hit_rate is not None else "N/A"
    summary_text = (
        f"Entry Hit Rate: {entry_hit_rate_str} | "
        f"Win Rate: {summary['win_rate']:.1f}% | "
        f"Best: {summary['best_call']} | Worst: {summary['worst_call']}"
    )

    midday_section = format_midday_context_block(midday_data)

    critique_section = ""
    if critique:
        critique_section = f"""

## PREVIOUS ATTEMPT FAILED VALIDATION
{critique}
IMPORTANT: Fix ALL listed issues. Cross-check claims against PRE-COMPUTED RESULTS.
"""

    prompt = f"""Review these PRE-COMPUTED evaluations for {scan_date:%Y-%m-%d}.

## PRE-COMPUTED RESULTS (DO NOT change numbers)
{evals_text}

## PRE-COMPUTED SUMMARY
{summary_text}

{midday_section}
{critique_section}
Your job:
1. Write a brief analysis for each ticker explaining WHY the outcome happened.
2. For each non-WIN outcome, classify the error_type:
   - ANALYSIS_ERROR: Thesis was wrong (direction_correct=False → wrong call)
   - EXECUTION_ERROR: Direction right but stop/timing off (direction_correct=True + stop_hit=True → tight stop)
   - VARIANCE: Setup sound, market didn't cooperate (direction_correct=True but price action random)
   - N/A: WIN or EXCLUDED tickers
3. For ANALYSIS_ERROR and EXECUTION_ERROR, add a one-line lesson.
4. Provide key_insight summarizing the day's most important lesson.

If midday data is provided, evaluate whether afternoon adjustments were helpful.
"""

    for attempt in range(2):
        try:
            agent, config = await create_commentary_agent()
            # HOOK-ALLOW: unguarded-agent-run reason=retro commentary runs post-market, non-blocking;
            # explicit 2-attempt retry + 5s backoff handles transient provider flakes.
            result = await agent.run(
                prompt,
                deps=AgentDeps(scan_date=scan_date, agent_key=config.agent_key),
                usage_limits=build_usage_limits(config),
            )
            return result.output
        except Exception as e:
            if attempt == 0:
                logger.warning("Commentary agent failed (attempt 1): %s — retrying in 5s", e)
                await asyncio.sleep(5)
            else:
                logger.error("Commentary agent failed after 2 attempts: %s", e)
                return None


# ============================================================================
# Formatting helpers
# ============================================================================


def format_midday_context_block(midday_data: dict | None) -> str:
    """Render midday position_alerts + recommendation_overrides as a prompt
    block so the retro_eval_critic and retro_commentary agents share the
    exact same midday context (SWI-141 / Fix 4).

    Returns empty string when midday data is missing — callers concatenate
    the result and an empty block contributes nothing.
    """
    if not midday_data:
        return ""
    afternoon_plan_prose = format_afternoon_plan_prose(
        midday_data.get("afternoon_plan") or [],
        midday_data.get("afternoon_note"),
    )
    section = f"""
## MIDDAY DATA
Trading Mode: {midday_data.get("trading_mode") or "N/A"}
Afternoon Plan: {afternoon_plan_prose}
Entries Hit at Midday: {len(midday_data.get("entries_hit") or [])}
"""
    overrides = midday_data.get("recommendation_overrides") or []
    if overrides:
        override_lines = []
        for o in overrides:
            if not isinstance(o, dict):
                logger.warning(
                    "Skipping non-dict recommendation_override: %s (type=%s)",
                    o,
                    type(o).__name__,
                )
                continue
            status = o.get("midday_status") or "?"
            ticker = o.get("ticker") or "?"
            morning = o.get("morning_action") or "?"
            reason = (o.get("reason") or "")[:60]
            # SWI-255: CANCEL is a signal cancellation, NOT an execution.
            # Phrasing must keep the LLM from treating reason text as a fact
            # of execution (no broker writes occurred at midday).
            if status.upper() == "CANCEL":
                override_lines.append(
                    f"  {ticker}: {morning} → CANCEL (signal cancellation; reason: {reason})"
                )
            else:
                override_lines.append(f"  {ticker}: {morning} → {status} ({reason})")
        section += "Recommendation Overrides:\n" + "\n".join(override_lines) + "\n"

    position_alerts = midday_data.get("position_alerts") or []
    if position_alerts:
        alert_lines = []
        for alert in position_alerts:
            if not isinstance(alert, dict):
                logger.warning(
                    "Skipping non-dict position_alert: %s (type=%s)",
                    alert,
                    type(alert).__name__,
                )
                continue
            alert_ticker = alert.get("ticker") or "?"
            level_type = alert.get("level_type") or "unknown"
            level = alert.get("level") or 0
            urgency = alert.get("urgency") or "unknown"
            alert_lines.append(f"  {alert_ticker}: {level_type} at {level:.1f}k ({urgency})")
        section += "Position Alerts:\n" + "\n".join(alert_lines) + "\n"
    return section


def format_evals_for_llm(evaluations: list[dict]) -> str:
    """Format pre-computed evaluations as text for LLM context.

    Each ticker line surfaces `plan_type` and `rule_applied` so the LLM
    narrative stays plan-type-aware (MON-2026-04-22-007) — the rule label
    comes from the Python post-pass, the LLM only reads it.
    """
    lines = []
    for e in evaluations:
        plan_type = e.get("plan_type") or "SWING"
        rule_applied = e.get("rule_applied") or "UNCLASSIFIED"
        entry = "entry_hit" if e["entry_hit"] else "missed"
        stop = " stop_hit" if e["stop_hit"] else ""
        target = " target_hit" if e["target_hit"] else ""

        pnl_parts = []
        pnl = e.get("pnl_percent")
        if pnl is not None and pnl != 0:
            pnl_parts.append(f"P/L:{pnl:+.1f}%")
        day = e.get("day_change")
        if day is not None:
            pnl_parts.append(f"day:{day:+.1f}%")
        prev_close = e.get("prev_close")
        if prev_close is not None:
            pnl_parts.append(f"prev:{format_kvnd(prev_close)}")
        pnl_str = f" {' '.join(pnl_parts)}" if pnl_parts else ""

        hints = []
        dc = e.get("direction_correct")
        sb = e.get("stop_buffer_pct")
        atr_ratio = e.get("stop_vs_atr_ratio")
        entry_gap = e.get("entry_gap_pct")
        pred_rr = e.get("predicted_rr")
        if dc is not None:
            hints.append(f"direction={'correct' if dc else 'wrong'}")
        if sb is not None:
            hints.append(f"stop_buffer={sb:.1f}%")
        if atr_ratio is not None:
            hints.append(f"stop/ATR={atr_ratio:.2f}")
        if entry_gap is not None:
            hints.append(f"entry_gap={entry_gap:+.1f}%")
        if pred_rr is not None:
            hints.append(f"pred_rr={pred_rr:.1f}")
        # For EXCLUDED tickers, show entry zone distance to enable meaningful analysis
        if (
            e.get("status") == "EXCLUDED"
            and e.get("entry_price")
            and e["entry_price"] > 0
            and e.get("eod_price")
        ):
            entry_zone = e["entry_price"]
            distance_pct = round((e["eod_price"] - entry_zone) / entry_zone * 100, 1)
            hints.append(f"entry_zone={format_kvnd(entry_zone)} distance={distance_pct:+.1f}%")
        if e.get("trade_executed"):
            actual_exit = e.get("actual_exit_price_vnd") or 0
            actual_pl = e.get("actual_pl_pct") or 0.0
            # actual_exit_price_vnd is raw BIGINT VND; convert to kVND for
            # a uniform display shape across the line (SWI-255).
            hints.append(f"EXECUTED exit={format_kvnd(actual_exit / 1000)} pl={actual_pl:+.2f}%")
        else:
            # Surface absence as a load-bearing signal (SWI-255). Silent absence
            # was the root of the ACV "executed correctly" fabrication.
            hints.append("NOT_EXECUTED")
        hints_str = f" [{', '.join(hints)}]" if hints else ""
        lines.append(
            f"- {e['ticker']} ({plan_type}): {e['recommendation']} → {e['status']}"
            f" ({entry}{stop}{target}{pnl_str})"
            f" EOD:{format_kvnd(e['eod_price'])} rule={rule_applied}{hints_str}"
        )
    return "\n".join(lines)
