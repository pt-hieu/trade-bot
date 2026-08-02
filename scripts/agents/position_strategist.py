#!/usr/bin/env python3
"""
Position Strategist Agent — owns POSITION GUIDANCE section of morning brief.

Focused entirely on existing portfolio positions: what to do with each holding.
Separated from entry_strategist to avoid diluting context with opposing concerns.
"""

from datetime import date

from pydantic_ai import Agent

from shared.agent_config import load_agent_config

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout


async def create_position_strategist_agent() -> Agent[AgentDeps, str]:
    """Create position strategist agent from DB config."""
    config = await load_agent_config("position_strategist")
    return create_agent(config)


async def generate_position_guidance(
    phase2_results: dict,
    trailing_stops_context: str = "",
    scan_date: date | None = None,
    geopolitical_context: str = "",
    portfolio_context: str = "",
    regime_context: str = "",
) -> str:
    """Generate POSITION GUIDANCE section for the morning brief.

    Args:
        phase2_results: Phase 2 output (position_alerts, sector_rotation)
        trailing_stops_context: Pre-computed trailing stops for holdings
        scan_date: Date for analysis

    Returns:
        Formatted POSITION GUIDANCE section string
    """
    if scan_date is None:
        scan_date = date.today()

    pos_alerts = phase2_results.get("position_alerts") or {}
    alerts = pos_alerts.get("alerts", [])
    agent = await create_position_strategist_agent()

    # Build context
    parts = []

    if regime_context:
        parts.append(regime_context)

    if geopolitical_context:
        parts.append(geopolitical_context)

    if trailing_stops_context:
        parts.append(
            "## PRE-COMPUTED TRAILING STOPS (use EXACTLY, do not override)\n"
            + trailing_stops_context
        )

    if alerts:
        alert_lines = []
        for a in alerts:
            line = f"  {a['ticker']}: {a['action']} ({a['urgency']}) — {a['reason']}"
            consensus = a.get("consensus")
            if consensus:
                line += f" [consensus: {consensus}]"
            dissent = a.get("dissenting_views", [])
            if dissent:
                line += "\n    Dissent: " + "; ".join(dissent)
            alert_lines.append(line)
        parts.append("## POSITION ALERTS FROM ENSEMBLE\n" + "\n".join(alert_lines))

    # Inject position beliefs for conviction-backed guidance
    position_beliefs = phase2_results.get("position_beliefs") or []
    if position_beliefs:
        from shared.formatting import format_belief_lines

        belief_lines = format_belief_lines(position_beliefs)
        parts.append("## POSITION BELIEFS (from analyst ensemble)\n" + "\n".join(belief_lines))

    rotation = phase2_results.get("sector_rotation")
    if rotation:
        hot = rotation.get("hot_sectors", [])
        cold = rotation.get("cold_sectors", [])
        parts.append(
            f"## SECTOR ROTATION\n"
            f"Hot: {', '.join(hot) or 'None'} | Cold: {', '.join(cold) or 'None'}"
        )

    if portfolio_context:
        from pipeline.context_blocks import PORTFOLIO_HEADER

        parts.insert(
            0,
            PORTFOLIO_HEADER + "\n" + portfolio_context,
        )

    context = "\n\n".join(parts)

    prompt = (
        f"Generate POSITION GUIDANCE section for {scan_date.strftime('%Y-%m-%d')}.\n\n"
        f"{context}\n\n"
        "Output ONLY the POSITION GUIDANCE section (one line per holding).\n"
        "PLAIN ASCII only, no markdown."
    )

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        deps = AgentDeps(scan_date=scan_date, agent_key="position_strategist")
        result = await run_agent_with_total_timeout(
            agent,
            prompt,
            agent_name="position_strategist",
            deps=deps,
            total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
        )
        return result.output
    except Exception as e:
        # Fallback: format from alerts
        if alerts:
            lines = ["POSITION GUIDANCE"]
            for a in alerts:
                lines.append(f"- {a['ticker']}: {a['action']} — {a.get('reason', 'see alerts')}")
            return "\n".join(lines)
        return f"POSITION GUIDANCE\n- Unable to generate: {e}"
