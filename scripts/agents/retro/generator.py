#!/usr/bin/env python3
"""
Retrospective Generator Agent using PydanticAI.

Generates human-readable retrospective from parsed data.
"""

import asyncio
import logging
import re
from datetime import date

from pydantic_ai import Agent

from midday.formatter import format_afternoon_plan_prose
from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config
from shared.neon.insert_learnings import normalize_rate

from ..agent_factory import AgentDeps, create_agent
from ..model.wrappers import OUTER_FALLBACK_STACK_WALL_S, await_with_hop_unwrap
from .compute import ENTRY_HIT_RATE_NA
from .parser import SECTION_TOP_PICKS

logger = logging.getLogger(__name__)

# Cap on the rec list injected into the retro prompt. Every BUY and every
# TOP_PICKS-section rec is included unconditionally; the remainder fills a
# WATCH/LONGTERM tail up to this total. Well under the <=7K context budget
# (each rec is one ~40-char line).
_RETRO_RECS_MAX_TOTAL = 12


def select_recs_for_retro(
    recommendations: list[dict], max_total: int = _RETRO_RECS_MAX_TOTAL
) -> list[dict]:
    """Partition morning recs for the retro prompt.

    Includes EVERY rec whose action is a BUY action, plus EVERY
    TOP_PICKS-section rec, unconditionally — then appends a WATCH/LONGTERM
    tail up to ``max_total``. Because BUY/TOP_PICKS recs are always kept
    regardless of input order, the DB fetch order (`ORDER BY section,
    ticker`, alphabetic) can no longer starve TOP_PICKS BUYs out of the
    slice — the run2 2026-05-14 defect where 10 alphabetic LONG_TERM rows
    filled all slots and the retro narrated "0 BUY".
    """
    from pipeline.recommendation_builder import BUY_ACTIONS

    primary: list[dict] = []
    tail: list[dict] = []
    for rec in recommendations:
        if rec.get("action") in BUY_ACTIONS or rec.get("section") == SECTION_TOP_PICKS:
            primary.append(rec)
        else:
            tail.append(rec)
    remaining = max(0, max_total - len(primary))
    return primary + tail[:remaining]


def _validate_retro_output(text: str) -> str:
    """Post-validate retro for arithmetic errors and small-sample rule proposals."""
    warnings: list[str] = []

    # Check 1: Flag arithmetic claims that don't add up
    # Match "55M x 4% = 7.3M" or "recovers 7.3M" style patterns
    for m in re.finditer(
        r"(\d+\.?\d*)M.*?(\d+\.?\d*)%.*?(?:=|recovers?|gains?)\s*(\d+\.?\d*)M",
        text,
        re.IGNORECASE,
    ):
        capital, pct, result = float(m.group(1)), float(m.group(2)), float(m.group(3))
        expected = capital * pct / 100
        if abs(expected - result) > 0.5:
            warnings.append(f"[MATH ERROR] {capital}M x {pct}% = {expected:.1f}M (not {result}M)")

    # Check 2: Flag rule proposals citing n<10
    for m in re.finditer(r"Rule:.*?n\s*=\s*(\d+)", text, re.IGNORECASE):
        n = int(m.group(1))
        if n < 10:
            warnings.append(
                f"[SMALL SAMPLE] Rule proposed on n={n} — insufficient for parameter changes"
            )

    if warnings:
        text += "\n\nPIPELINE VALIDATION WARNINGS\n" + "\n".join(f"- {w}" for w in warnings)

    return text


async def create_generator_agent() -> tuple[Agent[AgentDeps, str], AgentConfig]:
    """Create a retrospective generator agent."""
    config = await load_agent_config("retro_generator")
    # HOOK-ALLOW: no-tickers-scope (retro generator narrates the day's outcomes)
    agent = create_agent(config)
    return agent, config


async def generate_retro_with_agent(
    recommendations: list[dict],
    evaluations: dict,
    patterns: dict,
    midday_data: dict | None = None,
    strategy_directive: dict | None = None,
    streak_alert: dict | None = None,
    scan_date: date | None = None,
    buy_rec_count: int | None = None,
) -> str:
    """
    Generate human-readable retrospective using agent.

    Args:
        recommendations: Parsed recommendations from parser
        evaluations: Evaluation results with day_summary
        patterns: Extracted patterns from history
        midday_data: Optional midday check data
        strategy_directive: Optional strategy directive (contains goal info)
        streak_alert: Optional 0-BUY streak blob from
            ``agents.retro.streak.detect_zero_buy_streak``. When present,
            forces the retro to include a STREAK ALERT section.
        scan_date: Market close date — prompt-injection ONLY (pins the
            header date; the agent carries ``# HOOK-ALLOW: no-tickers-scope``
            so this must NOT scope tool calls — ``deps`` keeps scan_date=None).
        buy_rec_count: Deterministic count of BUY recs in the morning brief
            for ``scan_date``. Injected as a cite-verbatim fact so the
            narrated count cannot drift from the structural fact.

    Returns:
        Retrospective plain text string
    """
    evals = evaluations.get("evaluations", [])
    summary = evaluations.get("day_summary", {})
    midday_summary = evaluations.get("midday_summary")
    adjustment_effectiveness = evaluations.get("adjustment_effectiveness", "N/A")
    trading_mode = evaluations.get("trading_mode", "N/A")
    mode_compliance = evaluations.get("mode_compliance", True)
    mode_violations = evaluations.get("mode_violations", [])
    mode_counterfactual = evaluations.get("mode_counterfactual", {})

    # Format recommendations summary. Partition keeps every BUY/TOP_PICKS
    # rec — order-independent, so alphabetic DB ordering can't drop them.
    recs_str = ""
    for r in select_recs_for_retro(recommendations):
        action = r.get("action", "?")
        entry = r.get("entry_price")
        entry_str = f" @ {entry:,.0f}" if entry else ""
        recs_str += f"- {r['ticker']}: {action}{entry_str}\n"

    # Format evaluations summary
    evals_str = ""
    for e in evals[:10]:
        status = e.get("status", "?")
        pnl = e.get("pnl_percent", 0)
        pnl_str = f" ({pnl:+.1f}%)" if pnl else ""
        analysis = (e.get("analysis") or "")[:50]
        evals_str += f"- {e['ticker']}: {status}{pnl_str} - {analysis}\n"

    # Format day summary
    entry_hit_rate_raw = summary.get("entry_hit_rate")
    win_rate = summary.get("win_rate", 0)
    if entry_hit_rate_raw is not None:
        entry_hit_rate = normalize_rate(entry_hit_rate_raw)
        entry_hit_display = f"{entry_hit_rate:.0%}"
    else:
        entry_hit_display = ENTRY_HIT_RATE_NA
    win_rate = normalize_rate(win_rate) or 0
    summary_str = f"""Total: {summary.get("total_recs", 0)} recs
Entry Hit Rate: {entry_hit_display}
Win Rate: {win_rate:.0%}
Best: {summary.get("best_call", "N/A")}
Worst: {summary.get("worst_call", "N/A")}
Key Insight: {summary.get("key_insight", "N/A")}"""

    # Format patterns summary
    patterns_str = ""
    for p in patterns.get("winning_patterns", [])[:3]:
        win_rate = p.get("win_rate", 0)
        sample = p.get("sample_size", 0)
        patterns_str += f"WIN: {p['pattern']} ({win_rate:.0%}, n={sample})\n"
    for p in patterns.get("losing_patterns", [])[:2]:
        loss_rate = p.get("loss_rate", 0)
        sample = p.get("sample_size", 0)
        patterns_str += f"LOSE: {p['pattern']} ({loss_rate:.0%}, n={sample})\n"

    if not patterns_str:
        patterns_str = "Insufficient history for pattern extraction"

    # Format actionable rules
    actionable_rules = patterns.get("actionable_rules", [])
    rules_str = ""
    if actionable_rules:
        rules_str = "\nACTIONABLE RULES FROM PATTERNS:\n"
        for r in actionable_rules:
            rules_str += f"- Rule: {r['rule']} | Evidence: {r['evidence']}\n"

    # Format mode counterfactual
    counterfactual_str = ""
    if mode_counterfactual and mode_counterfactual.get("blocked_trades"):
        blocked = mode_counterfactual["blocked_trades"]
        blocked_lines = " | ".join(
            f"{b['ticker']} {b['day_change_pct']:+.1f}% ({'win' if b['would_win'] else 'loss'})"
            for b in blocked
        )
        correct_label = "CORRECT" if mode_counterfactual.get("mode_was_correct") else "INCORRECT"
        counterfactual_str = (
            f"\nMode blocked {len(blocked)} entries: {blocked_lines}\n"
            f"Net impact of blocked trades: {mode_counterfactual.get('net_impact', '0%')} "
            f"({mode_counterfactual.get('blocked_wins', 0)}W/{mode_counterfactual.get('blocked_losses', 0)}L) "
            f"Mode decision: {correct_label}"
        )

    # Format midday section if available
    midday_str = ""
    if midday_data:
        afternoon_plan_prose = format_afternoon_plan_prose(
            midday_data.get("afternoon_plan") or [],
            midday_data.get("afternoon_note"),
        )
        midday_str = f"""
MIDDAY CHECK:
Trading Mode: {trading_mode}
Afternoon Plan: {afternoon_plan_prose[:100]}
Adjustment Effectiveness: {adjustment_effectiveness}
Mode Compliance: {"Yes" if mode_compliance else "No"}
Violations: {", ".join(mode_violations) if mode_violations else "None"}
{counterfactual_str}"""
        if midday_summary:
            midday_str += f"""
Adjustments Made: {midday_summary.get("adjustments_made", 0)}
Helpful: {midday_summary.get("adjustments_helpful", 0)}
Harmful: {midday_summary.get("adjustments_harmful", 0)}
Key Adjustment: {midday_summary.get("key_adjustment", "N/A")}
"""

    # Format strategy directive if available
    directive_str = ""
    if strategy_directive:
        directive_str = f"""
STRATEGY DIRECTIVE FOR TODAY:
{strategy_directive.get("directive", "")}
Constraints: {strategy_directive.get("constraints", {})}
"""

    # Pre-compute goal recovery math (Rule #9: Python computes, LLM cites)
    goal_math_str = ""
    if strategy_directive:
        constraints = strategy_directive.get("constraints", {})
        goal_gap = constraints.get("goal_gap") or 0
        deployable = constraints.get("deployable") or summary.get("deployable_cash") or 0
        if deployable > 0 and goal_gap > 0:
            pct_needed = goal_gap / deployable * 100
            recovery_at_4pct = deployable * 0.04
            goal_math_str = (
                f"\nGOAL MATH (pre-computed, cite these — do NOT recalculate):\n"
                f"- Deployable: {deployable / 1e6:.1f}M VND\n"
                f"- Gap to goal: {goal_gap / 1e6:.1f}M VND\n"
                f"- Need {pct_needed:.1f}% return on full deployment to close gap\n"
                f"- One 4% winner on full deployment = {recovery_at_4pct / 1e6:.1f}M VND\n"
            )

    # Format streak alert (deterministic, pre-computed by Python)
    streak_str = ""
    if streak_alert and (streak_alert.get("length") or 0) >= 3:
        streak_str = (
            f"\nSTREAK ALERT (deterministic, cite verbatim):\n"
            f"- Length: {streak_alert['length']} consecutive 0-BUY days\n"
            f"- Started: {streak_alert.get('start_date', 'unknown')}\n"
            f"- Gate profile: {streak_alert.get('gate_profile', 'unknown')}\n"
        )

    # Authoritative header date (Rule #9: Python computes, LLM cites verbatim).
    date_str = ""
    if scan_date is not None:
        date_str = f"\nMARKET CLOSE DATE (use verbatim in the header): {scan_date}\n"

    # Deterministic BUY count — closes the inference path where the LLM
    # counts BUY lines in prose and drifts from the structural fact.
    buy_count_str = ""
    if buy_rec_count is not None:
        buy_count_str = (
            f"\nBUY COUNT (deterministic, cite verbatim — do NOT recount): "
            f"Morning brief produced {buy_rec_count} BUY recommendations today\n"
        )

    agent, config = await create_generator_agent()

    prompt = f"""Generate a market close retrospective.
{date_str}{buy_count_str}
MORNING RECOMMENDATIONS:
{recs_str or "No recommendations"}

END OF DAY RESULTS:
{evals_str or "No evaluations"}

DAY SUMMARY:
{summary_str}
{streak_str}{midday_str}{directive_str}
PATTERNS FROM LAST 7 DAYS:
{patterns_str}
{rules_str}{goal_math_str}
Write in PLAIN ASCII for Telegram. Keep it SHORT and actionable.
{"Include MIDDAY ADJUSTMENTS section since midday data was provided." if midday_data else "Skip MIDDAY ADJUSTMENTS section (no midday data)."}
{"Include STRATEGY DIRECTIVE REVIEW: Was the directive's stance correct? Did focus sectors outperform? Was the key risk managed? Include GOAL TRACKING if directive contains goal data." if strategy_directive else ""}
{"Include a STREAK ALERT section that cites the streak length, start date, and gate profile verbatim from the data above. Recommend reviewing the named gate's threshold." if streak_str else ""}"""

    # Retry loop for non-HTTP errors only (FallbackModel handles provider failover)
    for attempt in range(2):
        # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
        try:
            # HOOK-ALLOW: unguarded-agent-run reason=wrapped via asyncio.wait_for below
            result = await await_with_hop_unwrap(
                agent.run(
                    prompt,
                    deps=AgentDeps(scan_date=None, agent_key=config.agent_key),
                    usage_limits=build_usage_limits(config),
                ),
                timeout=int(OUTER_FALLBACK_STACK_WALL_S),
            )
            return _validate_retro_output(result.output)
        except Exception as e:
            if attempt == 0:
                logger.warning("Retro generator failed (attempt 1): %s — retrying in 5s", e)
                await asyncio.sleep(5)
            else:
                logger.error("Retro generator failed after 2 attempts: %s", e)
                raise
    raise RuntimeError("Retro generator: exhausted retry loop without returning")
