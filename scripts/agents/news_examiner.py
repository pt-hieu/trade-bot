"""
News Examiner Agent using PydanticAI.

Classifies keyword-matched articles as catalyst, capital_event, both, or irrelevant.
Extracts facts and affected tickers for downstream discovery agents.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from pydantic import BaseModel
from pydantic_ai import Agent

from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config
from shared.anchor_tickers import prime_and_render_vn_prompt_header
from shared.vn_universe import filter_vn_tickers

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout

logger = logging.getLogger(__name__)


class ArticleClassification(BaseModel):
    """Classification result for a single article."""

    article_id: str
    classification: str  # "catalyst", "capital_event", "both", "irrelevant"
    extracted_facts: list[str]
    affected_tickers: list[str]
    confidence: str  # HIGH, MEDIUM, LOW


class NewsExamination(BaseModel):
    """Complete news examination result."""

    classifications: list[ArticleClassification]


async def create_news_examiner_agent() -> tuple[Agent[AgentDeps, NewsExamination], AgentConfig]:
    """Create the news examiner agent (no tools — all context in prompt)."""
    config = await load_agent_config("news_examiner")
    # HOOK-ALLOW: no-tickers-scope (news_examiner discovers tickers from news)
    agent = create_agent(config, output_type=NewsExamination)
    return agent, config


async def examine_articles(
    filtered_articles: list[dict],
    scan_date: date | None = None,
) -> NewsExamination:
    """Classify a list of keyword-matched articles.

    Args:
        filtered_articles: Articles from filter_articles() — each has
            id, title, summary, source, matched_keywords
        scan_date: Date context for the examination

    Returns:
        NewsExamination with classifications per article
    """
    if not filtered_articles:
        return NewsExamination(classifications=[])

    agent, config = await create_news_examiner_agent()

    vn_header = await prime_and_render_vn_prompt_header()

    articles_text = []
    for art in filtered_articles:
        keywords = ", ".join(art.get("matched_keywords", []))
        articles_text.append(
            f"ID: {art['id']}\n"
            f"Title: {art['title']}\n"
            f"Summary: {(art.get('summary') or '')[:600]}\n"
            f"Source: {art.get('source', '')}\n"
            f"Matched keywords: {keywords}"
        )

    prompt = f"""{vn_header}

Classify these Vietnamese market news articles.

DATE: {scan_date or date.today()}

ARTICLES:
{"=" * 60}
{chr(10).join(chr(10).join(["", a, "---"]) for a in articles_text)}

For each article, classify as:
- "catalyst": Regulatory/macro catalyst affecting market (policy changes, index upgrades, government spending, FDI, banking rules)
- "capital_event": Company-level capital action (IPO, rights issue, dividend, merger, buyback, stock split)
- "both": Article covers both types
- "irrelevant": Matched keywords by coincidence, no real market impact

Extract:
- extracted_facts: Key facts from the article (dates, amounts, tickers, decisions)
- affected_tickers: VN-listed stock codes from the anchor + hint map above,
  OR the literal placeholder ["VN-INDEX"] for macro/geopolitical events that
  affect the Vietnamese market broadly. Never invent non-VN codes (US, HK,
  EU) — leave the list empty if no VN-listed ticker is clearly implicated
  and the event is not a market-wide macro catalyst.
- confidence: HIGH (official announcement), MEDIUM (credible report), LOW (rumor/unclear)

Classify ALL {len(filtered_articles)} articles."""

    for attempt in range(2):
        # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
        try:
            result = await run_agent_with_total_timeout(
                agent,
                prompt,
                agent_name="news_examiner",
                deps=AgentDeps(scan_date=None, agent_key="news_examiner"),
                total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
                usage_limits=build_usage_limits(config),
            )
            for entry in result.output.classifications:
                entry.affected_tickers = filter_vn_tickers(
                    entry.affected_tickers, context=f"news_examiner:{entry.article_id}"
                )
            return result.output
        except Exception as error:
            if attempt == 0:
                logger.warning("News examiner failed (attempt 1): %s — retrying in 5s", error)
                await asyncio.sleep(5)
            else:
                logger.warning(
                    "News examiner failed after 2 attempts: %s — returning empty classifications",
                    error,
                )
                from shared.telegram import send_telegram_error

                send_telegram_error(
                    f"News examiner failed after 2 attempts: {error} "
                    f"({len(filtered_articles)} articles lost)"
                )
                return NewsExamination(classifications=[])

    return NewsExamination(classifications=[])  # unreachable
