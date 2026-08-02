"""Subject-aware article sentiment scorer (SWI-103).

Replaces the keyword-based `shared.sentiment.score_sentiment_from_summary`
with an LLM that understands subject-of-action: "tax cut" reads positive,
"profit cut" reads negative. Returns both polarity score and a confidence
channel — downstream consumers (`narrative_matching.py`,
`narrative_mutations.py`) gate on `is_trusted(confidence)` so a single
wrong-sign LLM call cannot poison a narrative thread.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config
from shared.observability import span

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_DISABLE_FALLBACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout

logger = logging.getLogger(__name__)


class ArticleSentiment(BaseModel):
    """Subject-aware polarity + confidence for a single article."""

    sentiment_score: float = Field(ge=-1.0, le=1.0)
    confidence: Literal["high", "medium", "low", "abstain"]
    reasoning: str


# Per-process cache: building a PydanticAI Agent allocates the model client +
# structured-output validators. On a 500-article backfill rebuilding it per
# call is pure waste; the agent is stateless, so one instance is enough.
_AGENT_CACHE: tuple[AgentConfig, Agent[AgentDeps, ArticleSentiment]] | None = None


async def _get_agent() -> Agent[AgentDeps, ArticleSentiment]:
    global _AGENT_CACHE
    config = await load_agent_config("article_sentiment")
    if _AGENT_CACHE is not None and _AGENT_CACHE[0] is config:
        return _AGENT_CACHE[1]
    # HOOK-ALLOW: no-tickers-scope (article_sentiment classifies polarity, not ticker-scoped)
    agent = create_agent(config, output_type=ArticleSentiment)
    _AGENT_CACHE = (config, agent)
    return agent


async def score_article_sentiment(article: dict) -> ArticleSentiment | None:
    """Score one article with the LLM. Returns None on failure (caller writes NULL/NULL)."""
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    if not summary and not title:
        return None

    config = await load_agent_config("article_sentiment")
    agent = await _get_agent()

    prompt = (
        "Classify the polarity of this Vietnamese financial-news article.\n\n"
        f"Title: {title}\n"
        f"Summary: {summary}\n"
    )

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        with span("article_sentiment_scoring", url=str(article.get("url") or "")):
            result = await run_agent_with_total_timeout(
                agent,
                prompt,
                agent_name="article_sentiment",
                deps=AgentDeps(scan_date=None, agent_key="article_sentiment"),
                total_timeout_s=float(OUTER_DISABLE_FALLBACK_WALL_S),
                usage_limits=build_usage_limits(config),
            )
        return result.output
    except Exception as exc:
        logger.warning(
            "article_sentiment failed url=%s err=%s",
            article.get("url"),
            exc,
            exc_info=True,
        )
        return None
