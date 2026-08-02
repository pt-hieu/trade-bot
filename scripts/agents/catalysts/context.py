"""Agent factory + active-catalyst context formatter + discovery orchestrator."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from pydantic_ai import Agent

from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config
from shared.anchor_tickers import prime_and_render_vn_prompt_header
from shared.neon.catalyst_summaries import format_affected_tickers
from shared.neon.catalysts import get_active_catalysts_db
from shared.observability import span
from shared.vn_universe import filter_vn_tickers

from ..agent_factory import AgentDeps, create_agent
from ..model.wrappers import OUTER_FALLBACK_STACK_WALL_S, await_with_hop_unwrap
from .persist import _persist_discoveries
from .schemas import CatalystDiscovery

logger = logging.getLogger(__name__)


async def _create_catalyst_agent() -> tuple[Agent[AgentDeps, CatalystDiscovery], AgentConfig]:
    """Create a catalyst discovery agent.

    No tools are registered — current catalysts are injected into the
    prompt instead (CLAUDE.md "inject-first, tools-optional" rule).
    """
    config = await load_agent_config("catalysts")
    # HOOK-ALLOW: no-tickers-scope (catalysts discovers tickers from articles)
    agent = create_agent(config, output_type=CatalystDiscovery)
    return agent, config


def _format_active_catalysts_context(rows: list[dict]) -> str:
    """Render active catalysts as a plain-text block for prompt injection."""
    if not rows:
        return "ACTIVE CATALYSTS\n================\n(none — database is empty)\n"
    rows = [r for r in rows if (r.get("catalyst_type") or "") != "unclassified"]
    lines = ["ACTIVE CATALYSTS", "================"]
    for r in rows:
        tickers_str = format_affected_tickers(r.get("affected_tickers") or [])
        catalyst_type = r.get("catalyst_type") or "unknown"
        phases = r.get("phases") or {}
        phase_summary = ""
        if phases:
            phase_names = sorted(phases.keys())
            phase_summary = f" | phases: {', '.join(phase_names)}"
        lines.append(
            f"- id: {r['catalyst_key']} [{catalyst_type}] [{r.get('status') or 'active'}]\n"
            f"  event: {r['event']}\n"
            f"  expected: {r.get('expected') or 'ongoing'} | "
            f"impact: {r.get('impact') or 'NEUTRAL'} | "
            f"confidence: {r.get('confidence') or 'UNKNOWN'}{phase_summary}\n"
            f"  affected: {tickers_str}"
        )
    lines.append("")
    return "\n".join(lines)


async def discover_catalysts_with_agent(
    classified_articles: list[dict],
    scan_date: date | None = None,
) -> dict:
    """Discover catalysts from pre-classified article facts."""
    if scan_date is None:
        scan_date = date.today()

    agent, config = await _create_catalyst_agent()

    vn_header = await prime_and_render_vn_prompt_header()

    active_rows = await get_active_catalysts_db(None)
    active_context = _format_active_catalysts_context(active_rows)

    articles_text = []
    for art in classified_articles:
        facts = "\n".join(f"  - {f}" for f in art.get("extracted_facts", []))
        tickers = ", ".join(art.get("affected_tickers", [])) or "none identified"
        articles_text.append(
            f"Article {art['article_id']} [{art.get('confidence', 'MEDIUM')}]:\n"
            f"Facts:\n{facts}\n"
            f"Affected tickers: {tickers}"
        )

    prompt = f"""{vn_header}

Discover catalysts from pre-classified news facts.

DATE: {scan_date}

{active_context}

PRE-CLASSIFIED ARTICLE FACTS:
{"=" * 60}
{chr(10).join(chr(10).join(["", a, "---"]) for a in articles_text)}

## Your Tasks

For each article fact set above, identify:
  - New catalysts not yet tracked (emit CatalystAddition)
  - Updates to existing catalysts from the ACTIVE CATALYSTS list above — timeline
    shifts, phase transitions for geopolitical shocks, confidence upgrades
    (emit CatalystUpdate)
  - Catalysts that have been completed/resolved (emit CatalystCompletion)

Ticker discipline: output `affected` as VN-listed codes from the anchor + hint
map above. Macro, geopolitical, and commodity events that affect the
Vietnamese market broadly MUST use `affected=["VN-INDEX"]` — do NOT invent
ticker symbols, and do NOT list individual tickers you think the macro story
"transmits to"; downstream fan-out handles that deterministically.

Every addition MUST include `supporting_article_ids` naming the specific article_ids
above that evidence the catalyst — not all of them, just the ones that apply."""

    with span("catalyst_discovery", scan_date=str(scan_date)):
        for attempt in range(2):
            # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
            try:
                result = await await_with_hop_unwrap(
                    agent.run(
                        prompt,
                        deps=AgentDeps(scan_date=scan_date, agent_key=config.agent_key),
                        usage_limits=build_usage_limits(config),
                    ),
                    timeout=int(OUTER_FALLBACK_STACK_WALL_S),
                )
            except Exception as error:
                if attempt == 0:
                    logger.warning(
                        "Catalyst discovery failed (attempt 1): %s — retrying in 5s",
                        error,
                    )
                    await asyncio.sleep(5)
                    continue
                logger.warning(
                    "Catalyst discovery failed after 2 attempts: %s — returning empty",
                    error,
                )
                return {"additions": [], "updates": [], "completions": []}

            for addition in result.output.additions:
                addition.affected = filter_vn_tickers(
                    addition.affected, context=f"catalysts:{addition.event[:40]}"
                )
            discoveries = {
                "additions": [a.model_dump() for a in result.output.additions],
                "updates": [u.model_dump() for u in result.output.updates],
                "completions": [c.model_dump() for c in result.output.completions],
            }
            await _persist_discoveries(
                discoveries, scan_date, classified_articles, existing_catalysts=active_rows
            )
            return discoveries

        return {"additions": [], "updates": [], "completions": []}  # unreachable
