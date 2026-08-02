"""Deterministic section builder for strategy directive.

Builds pre-computed text blocks (GOAL PROGRESS, CAPITAL STATUS, etc.)
that are embedded verbatim in the LLM prompt. All arithmetic is Python —
the LLM only reads and reasons over these sections.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from shared.formatting import format_vnd
from shared.rules.geopolitical import ACTIVE_SHOCK_PHASES, GEOPOLITICAL_PHASES, SHOCK_MULTIPLIER_MAP
from shared.trading_config import get_trading_config

if TYPE_CHECKING:
    from shared.rules.constraints import PipelineConstraints

logger = logging.getLogger(__name__)

from .tools.portfolio import get_position_scale_factor


async def build_deterministic_sections(
    goals: list[dict],
    cash: dict,
    constraints: PipelineConstraints | dict,
    phase1: dict,
) -> str:
    """Build pre-computed deterministic sections.

    Sections: GOAL PROGRESS, CAPITAL STATUS, ENTRY CRITERIA TODAY,
    GLOBAL CONTEXT. These are concatenated verbatim into the final brief
    by the downstream renderer (phase_strategy.py). The LLM authors the
    narrative sections only.
    """
    parts = []

    # --- GOAL PROGRESS ---
    active_goals = [goal for goal in goals if "error" not in goal]
    if active_goals:
        goal_lines = ["GOAL PROGRESS"]
        for goal in active_goals:
            urgency_tag = (goal.get("urgency") or {}).get("urgency") or "NORMAL"
            realized = goal.get("realized") or 0
            target = goal.get("target") or 0
            progress = goal.get("progress_pct") or 0
            days_left = goal.get("days_left") or 0
            on_track = goal.get("on_track") or False
            goal_lines.append(
                f"- {goal.get('name') or '?'}: "
                f"{format_vnd(realized)}/{format_vnd(target)} VND "
                f"({progress:.1f}%) | {days_left} days left"
            )
            goal_lines.append(f"- Urgency: {urgency_tag}")
            achievability = goal.get("achievability")
            if achievability:
                goal_lines.append(
                    f"- Achievability: {achievability} — {goal.get('achievability_note') or ''}"
                )
            goal_lines.append(f"- Status: {'On track' if on_track else 'Behind schedule'}")
        parts.append("\n".join(goal_lines))
    else:
        parts.append("GOAL PROGRESS\n- No active goals")

    # --- CAPITAL STATUS ---
    config = get_trading_config()
    total_cash = cash.get("total_cash") or 0
    deployable = cash.get("deployable") or 0
    reserve = cash.get("min_reserve") or config.min_cash_reserve

    scale_data = await get_position_scale_factor()
    scale_factor = scale_data.get("scale_factor") or 1.0
    win_rate = scale_data.get("win_rate") or 50
    capital_lines = [
        "CAPITAL STATUS",
        f"- Cash: {format_vnd(total_cash)} | Reserve: {format_vnd(reserve)} | Deployable: {format_vnd(deployable)}",
        f"- Position Scale: {scale_factor:.2f}x (based on {win_rate:.0f}% win rate)",
    ]
    if deployable <= 0:
        capital_lines.append("- WARNING: No deployable cash — no new entries allowed")
    elif deployable < config.low_cash_threshold:
        capital_lines.append("- WARNING: Low cash — minimal entries only")
    parts.append("\n".join(capital_lines))

    # --- GLOBAL CONTEXT ---
    macro = phase1.get("macro_metrics")
    if macro and "error" not in macro:
        global_lines = [
            "GLOBAL CONTEXT",
            f"- DXY: {macro.get('dxy_value') or 'N/A'} ({macro.get('dxy_signal') or 'N/A'}) | "
            f"VIX: {macro.get('vix_value') or 'N/A'} ({macro.get('vix_signal') or 'N/A'}) | "
            f"USD/VND: {macro.get('usd_vnd_rate') or 'N/A'} ({macro.get('usd_vnd_signal') or 'N/A'})",
            f"- Risk Regime: {macro.get('global_risk_regime') or 'CAUTIOUS'}",
        ]
        oil_price = macro.get("oil_price")
        oil_signal = macro.get("oil_signal") or "N/A"
        oil_change = macro.get("oil_change_pct")
        if oil_price is not None:
            oil_str = f"- Oil: {oil_price:.1f} USD/bbl"
            if oil_change is not None:
                oil_str += f" ({oil_change:+.2f}%)"
            oil_str += f" → {oil_signal}"
            if oil_signal in ("ELEVATED", "ELEVATED_SPIKE", "EXTREME", "EXTREME_SPIKE"):
                oil_str += " — Oil-sensitive sectors (transport, manufacturing) at risk"
            global_lines.append(oil_str)
        events = macro.get("upcoming_events")
        if events:
            global_lines.append(f"- Upcoming: {', '.join(events)}")
        parts.append("\n".join(global_lines))

    # --- GEOPOLITICAL SHOCK PLAYBOOK ---
    geo_shock = phase1.get("macro_metrics", {}).get("geopolitical_shock")
    if geo_shock and geo_shock.get("phase_name") in ACTIVE_SHOCK_PHASES:
        phase_name = geo_shock["phase_name"]
        phase_config = GEOPOLITICAL_PHASES[phase_name]
        shock_multiplier = SHOCK_MULTIPLIER_MAP[phase_name]
        shock_lines = [
            "GEOPOLITICAL SHOCK PLAYBOOK",
            f"- Active: {geo_shock['catalyst_event']}",
            f"- Phase: {phase_config.context_header}",
            f"- Behavior: {geo_shock.get('behavior') or 'Monitor closely'}",
            "- CORRELATION WARNING: All sectors tend to correlate during geopolitical shocks. "
            "'Oil-agnostic' thesis does NOT hold in shock phases.",
        ]
        if phase_name == "immediate_shock":
            shock_lines.append(
                f"- POSITION SIZING: Reduce to {shock_multiplier}x shock multiplier on all new entries"
            )
            shock_lines.append(
                "- STOPS: Tighten all open position stops by 50% of current distance"
            )
        elif phase_name == "sustained_pressure":
            shock_lines.append(
                f"- POSITION SIZING: Reduce to {shock_multiplier}x shock multiplier on all new entries"
            )
            shock_lines.append("- STOPS: Review all open positions for energy cost exposure")
        elif phase_name == "resolution_or_escalation":
            shock_lines.append(
                f"- POSITION SIZING: Maintain {shock_multiplier}x position sizing on geo-sensitive names. "
                "Crisis in resolution/escalation phase — outcomes uncertain. "
                "Do not add new geo-driven directional entries."
            )
        affected_tickers = geo_shock.get("affected_tickers") or []
        if affected_tickers:
            shock_lines.append(f"- IMPACTED TICKERS: {', '.join(affected_tickers[:15])}")
        notes = geo_shock.get("notes") or ""
        if notes:
            shock_lines.append(f"- ANALYST NOTES: {notes}")
        parts.append("\n".join(shock_lines))

    # --- STRUCTURAL CATALYSTS / CAPITAL EVENTS / NARRATIVES (parallel) ---
    async def _safe_catalyst_summary() -> str | None:
        try:
            from shared.neon.catalyst_summaries import get_filtered_catalyst_summary

            text = await get_filtered_catalyst_summary()
            if text:
                return "STRUCTURAL CATALYSTS\n" + text
        except Exception as error:
            logger.warning("Failed to load catalyst summary: %s", error)
        return None

    async def _safe_capital_events_summary() -> str | None:
        try:
            from shared.neon.catalyst_summaries import get_capital_events_summary

            text = await get_capital_events_summary()
            if text and text != "No upcoming capital events tracked.":
                return "CAPITAL EVENTS\n" + text
        except Exception as error:
            logger.warning("Failed to load capital events summary: %s", error)
        return None

    async def _safe_narrative_summary() -> str | None:
        try:
            from shared.neon.narrative_summaries import get_narrative_summary

            text = await get_narrative_summary()
            if text:
                return "DEVELOPING NARRATIVES\n" + text
        except Exception as error:
            logger.warning("Failed to load narrative summary: %s", error)
        return None

    supplemental_results = await asyncio.gather(
        _safe_catalyst_summary(),
        _safe_capital_events_summary(),
        _safe_narrative_summary(),
    )
    for supplemental_text in supplemental_results:
        if supplemental_text:
            parts.append(supplemental_text)

    # --- RETRO CONSTRAINTS ---
    retro_text = constraints.get("retro_constraint_text")
    if retro_text:
        parts.append(retro_text)

    # --- ENTRY CRITERIA TODAY ---
    # Prefer the POST-composition values written by `inject_gate_composition`.
    # Fall back to the urgency inputs only when the composer hasn't run
    # (offline snapshots, legacy replays). This keeps the brief aligned with
    # `daily_record.gate_decision_json.effective_rr_floor` / `max_new_entries`.
    effective_max = (
        constraints.get("effective_max_new_entries") or constraints.get("max_new_entries") or 3
    )
    effective_min_rr = constraints.get("effective_min_rr") or constraints.get("min_rr") or 2.5

    urgency_tier = constraints.get("urgency_tier") or "NORMAL"
    entry_lines = [
        "ENTRY CRITERIA TODAY",
        f"- Min R:R: {effective_min_rr} | Max entries: {effective_max} | Budget: {format_vnd(constraints.get('budget_vnd') or 0)}",
    ]
    if not constraints.get("entries_allowed", True):
        blocked_reason = constraints.get("entries_blocked_reason") or "Unknown"
        entry_lines.append(f"- BLOCKED: {blocked_reason}")
        entry_lines.append("- No new entries today — focus on managing existing positions")
    if urgency_tier == "DETERMINED":
        entry_lines.append(
            f"- Quality bar: SELECTIVE — R:R >= {effective_min_rr}, max {effective_max} entries "
            "(goal behind but keep hunting — one disciplined trade breaks the streak)"
        )
    elif urgency_tier == "ACCEPTANCE":
        entry_lines.append(
            f"- Quality bar: SELECTIVE — R:R >= {effective_min_rr}, max {effective_max} entries "
            "required (month nearly over — quality entries only, don't stop hunting)"
        )
    elif urgency_tier == "HIGH":
        entry_lines.append(
            f"- Quality bar: A+ setups only, R:R >= {effective_min_rr} (HIGH urgency)"
        )
    elif urgency_tier == "ELEVATED":
        entry_lines.append(
            f"- Quality bar: High-conviction setups, R:R >= {effective_min_rr} (ELEVATED urgency)"
        )
    else:
        entry_lines.append("- Quality bar: Standard — valid R:R + regime alignment")
    parts.append("\n".join(entry_lines))

    return "\n\n".join(parts)
