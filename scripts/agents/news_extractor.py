"""News v2 Stage 2 — extractor + classifier (SWI-243).

Per-article LLM call that emits four orthogonal facts as one structured
output: affected tickers, narrative attachment, catalyst attachment,
sentiment polarity. Receives candidates-only context (≤10 rows) plus
active narratives + active catalysts (last 14d) — fits inside the 7K
injected-tokens budget per CLAUDE.md.

LLM emits raw `str` for the seven enum fields; the post-LLM coercion
layer in ``shared/rules/news_v2_coercion.py`` collapses unknowns to the
``unclassified`` sentinel and emits ``post_llm_rule.unclassified`` so
operators can watch the rate climb.

Cross-run merge stays Python-owned (CLAUDE.md "Python / LLM split"):
  * `narrative_match_key` → existing-narrative-key lookup, then embedding
    match via ``data/narrative_matching.match_existing_narrative`` for
    semantic neighbours, then create-new fallback.
  * `catalyst_event_phrase` → ``compose_catalyst_key`` slug+md5 dedup.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from shared.agent_config import (
    LLM_LABELING_CONCURRENCY,
    AgentConfig,
    build_usage_limits,
    load_agent_config,
)
from shared.observability import span
from shared.rules.news_v2_coercion import (
    coerce_capital_event_type,
    coerce_catalyst_confidence,
    coerce_catalyst_impact,
    coerce_catalyst_type,
    coerce_link_kind,
    coerce_narrative_type,
    coerce_sentiment_confidence,
)

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout

logger = logging.getLogger(__name__)


class NewsExtractionRaw(BaseModel):
    """LLM-emitted raw extraction. Enum fields are `str`; Python coerces."""

    # HOOK-ALLOW: empty-output-permitted reason=article may name no VN tickers
    affected_tickers: list[str] = Field(default_factory=list, max_length=20)

    narrative_link_kind: str = "NONE"
    narrative_match_key: str | None = None
    narrative_type: str = ""

    catalyst_link_kind: str = "NONE"
    catalyst_event_phrase: str | None = None
    catalyst_type: str = ""
    catalyst_impact: str = ""
    catalyst_confidence: str = ""

    sentiment_score: float = Field(ge=-1.0, le=1.0, default=0.0)
    sentiment_confidence: str = ""

    capital_event: bool = False
    capital_event_type: str | None = None

    abstain: bool = False
    abstain_reason: str | None = None


class NewsExtraction(BaseModel):
    """Coerced + universe-validated extraction ready for persistence."""

    affected_tickers: list[str]

    narrative_link_kind: Literal["EXISTING", "NEW", "NONE", "unclassified"]
    narrative_match_key: str | None
    narrative_type: str

    catalyst_link_kind: Literal["EXISTING", "NEW", "NONE", "unclassified"]
    catalyst_event_phrase: str | None
    catalyst_type: str
    catalyst_impact: Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "unclassified"]
    catalyst_confidence: Literal["HIGH", "MEDIUM", "LOW", "unclassified"]

    sentiment_score: float
    sentiment_confidence: Literal["HIGH", "MEDIUM", "LOW", "unclassified"]

    capital_event: bool
    capital_event_type: str | None

    abstain: bool
    abstain_reason: str | None


_AGENT_CACHE: tuple[AgentConfig, Agent[AgentDeps, NewsExtractionRaw]] | None = None


async def _get_agent() -> Agent[AgentDeps, NewsExtractionRaw]:
    global _AGENT_CACHE
    config = await load_agent_config("news_extractor")
    if _AGENT_CACHE is not None and _AGENT_CACHE[0] is config:
        return _AGENT_CACHE[1]
    # HOOK-ALLOW: no-tickers-scope (extractor receives candidates-only context per article)
    agent = create_agent(config, output_type=NewsExtractionRaw)
    _AGENT_CACHE = (config, agent)
    return agent


def _coerce_extraction(
    raw: NewsExtractionRaw,
    candidate_tickers: frozenset[str],
    universe_tickers: frozenset[str],
    article_url: str,
) -> NewsExtraction:
    """Apply Python-side invariants to a raw LLM output.

    * Enum fields → closed set via shared/rules/news_v2_coercion.
    * affected_tickers → ⊆ candidates ∪ universe ∪ {"VN-INDEX"}. Drops
      logged at INFO so the orchestrator can grep for hallucinations.
    """
    allowed = candidate_tickers | universe_tickers | {"VN-INDEX"}
    cleaned: list[str] = []
    dropped: list[str] = []
    for raw_ticker in raw.affected_tickers or []:
        ticker = (raw_ticker or "").strip().upper()
        if not ticker:
            continue
        if ticker in allowed:
            cleaned.append(ticker)
        else:
            dropped.append(ticker)
    if dropped:
        logger.info(
            "news_extractor: dropped non-candidate tickers url=%s drops=%s",
            article_url,
            dropped[:10],
        )

    return NewsExtraction(
        affected_tickers=cleaned,
        narrative_link_kind=coerce_link_kind(raw.narrative_link_kind),
        narrative_match_key=(raw.narrative_match_key or None) and raw.narrative_match_key.strip(),
        narrative_type=coerce_narrative_type(raw.narrative_type),
        catalyst_link_kind=coerce_link_kind(raw.catalyst_link_kind),
        catalyst_event_phrase=(raw.catalyst_event_phrase or None)
        and raw.catalyst_event_phrase.strip(),
        catalyst_type=coerce_catalyst_type(raw.catalyst_type),
        catalyst_impact=coerce_catalyst_impact(raw.catalyst_impact),
        catalyst_confidence=coerce_catalyst_confidence(raw.catalyst_confidence),
        sentiment_score=raw.sentiment_score,
        sentiment_confidence=coerce_sentiment_confidence(raw.sentiment_confidence),
        capital_event=raw.capital_event,
        capital_event_type=coerce_capital_event_type(raw.capital_event_type)
        if raw.capital_event
        else None,
        abstain=raw.abstain,
        abstain_reason=raw.abstain_reason,
    )


async def extract_one(
    article: dict,
    *,
    candidates_block: str,
    active_narratives_block: str,
    active_catalysts_block: str,
    candidate_tickers: frozenset[str],
    universe_tickers: frozenset[str],
) -> NewsExtraction | None:
    """Run Stage 2 on a single article. ``None`` on shape/timeout failure."""
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    if not (title or summary):
        return None

    config = await load_agent_config("news_extractor")
    agent = await _get_agent()
    prompt = (
        f"{candidates_block}\n\n"
        f"{active_narratives_block}\n\n"
        f"{active_catalysts_block}\n\n"
        "ARTICLE TO EXTRACT\n"
        f"Title: {title}\n"
        f"Summary: {summary}\n"
    )

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        with span("news_extractor_scoring", url=str(article.get("url") or "")):
            result = await run_agent_with_total_timeout(
                agent,
                prompt,
                agent_name="news_extractor",
                deps=AgentDeps(scan_date=None, agent_key="news_extractor"),
                total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
                usage_limits=build_usage_limits(config),
            )
    except Exception as exc:
        logger.warning(
            "news_extractor failed url=%s err=%s",
            article.get("url"),
            exc,
            exc_info=True,
        )
        return None

    return _coerce_extraction(
        result.output,
        candidate_tickers=candidate_tickers,
        universe_tickers=universe_tickers,
        article_url=str(article.get("url") or ""),
    )


async def extract_articles(
    routed_jobs: list[dict],
    *,
    universe_tickers: frozenset[str],
) -> list[tuple[dict, NewsExtraction | None]]:
    """Run Stage 2 on every routed article under shared semaphore.

    Each ``routed_jobs`` entry must carry these keys:

    * ``article``       — original article dict (url, title, summary, id)
    * ``candidates_block``         — pre-rendered Stage 2 candidate block
    * ``candidate_tickers``        — frozenset[str] of resolved tickers
    * ``active_narratives_block``  — batch-static block from Phase 0
    * ``active_catalysts_block``   — batch-static block from Phase 0
    """
    semaphore = asyncio.Semaphore(LLM_LABELING_CONCURRENCY)

    async def _one(job: dict) -> tuple[dict, NewsExtraction | None]:
        async with semaphore:
            extraction = await extract_one(
                job["article"],
                candidates_block=job["candidates_block"],
                active_narratives_block=job["active_narratives_block"],
                active_catalysts_block=job["active_catalysts_block"],
                candidate_tickers=job["candidate_tickers"],
                universe_tickers=universe_tickers,
            )
        return job["article"], extraction

    return await asyncio.gather(*(_one(j) for j in routed_jobs))


__all__ = [
    "NewsExtraction",
    "NewsExtractionRaw",
    "extract_articles",
    "extract_one",
]
