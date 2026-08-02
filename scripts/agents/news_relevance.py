"""News v2 Stage 1 — relevance gate + entity-candidate spotter (SWI-247).

Per-article LLM call run under a shared semaphore. Output drives two
things:

1. Routing — articles with ``is_vn_relevant=True`` (or ``LOW`` confidence,
   for recall rescue) flow to Stage 2; others are dropped with a bucketed
   reason.
2. Candidate entities — Stage 2 receives ONLY the entities Stage 1 spotted,
   resolved against ``company_profiles.aliases``. This is the lever that
   takes Stage 2's injected context from "full universe" (≥8K tokens) to
   "≤10 rows" — without it, the 7K injected budget cannot fit a per-article
   prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
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

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_DISABLE_FALLBACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout

logger = logging.getLogger(__name__)


class NewsRelevance(BaseModel):
    """Stage 1 verdict — persisted to ``articles.stage1_verdict`` JSONB."""

    is_vn_relevant: bool
    # HOOK-ALLOW: empty-output-permitted reason=article may name no VN entities
    candidate_entities: list[str] = Field(default_factory=list, max_length=8)
    relevance_confidence: Literal["HIGH", "MEDIUM", "LOW"]
    abstain_reason: str | None = None


@dataclass(frozen=True)
class Stage1Error:
    """Typed sentinel for Stage-1 hard failures (network/LLM exceptions).

    Distinct from ``None`` (shape-fail) so ``stage1_verdict`` JSONB records
    the failure class and is grep-able after the fact. Never routed to
    Stage 2 — Stage-1 had no chance to seed ``candidate_entities``.
    """

    error_class: str
    message: str  # truncated to 200 chars


# Union of every value Stage-1 can hand back to callers — pinning a single
# alias keeps signatures/docstrings honest as the discriminator evolves.
Stage1Outcome = NewsRelevance | Stage1Error | None


_AGENT_CACHE: tuple[AgentConfig, Agent[AgentDeps, NewsRelevance]] | None = None


async def _get_agent() -> Agent[AgentDeps, NewsRelevance]:
    global _AGENT_CACHE
    config = await load_agent_config("news_relevance")
    if _AGENT_CACHE is not None and _AGENT_CACHE[0] is config:
        return _AGENT_CACHE[1]
    # HOOK-ALLOW: no-tickers-scope (Stage 1 spots entity tokens, not tickers)
    agent = create_agent(config, output_type=NewsRelevance)
    _AGENT_CACHE = (config, agent)
    return agent


async def score_relevance_one(article: dict, universe_block: str) -> Stage1Outcome:
    """Score one article. Three-way return contract:

    * ``NewsRelevance`` — Stage-1 returned a valid verdict (route per
      ``routes_to_stage_two``).
    * ``None`` — shape-fail (article had no title and no summary). Routed
      to Stage 2 as a recall rescue.
    * ``Stage1Error`` — hard exception inside the agent call (network,
      timeout, LLM upstream). NOT routed to Stage 2 — Stage 1 never seeded
      ``candidate_entities`` so Stage 2 would run blind. Visible in
      ``stage1_verdict.error`` for audit.
    """
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    if not (title or summary):
        return None

    config = await load_agent_config("news_relevance")
    agent = await _get_agent()

    prompt = f"{universe_block}\n\nARTICLE TO CLASSIFY\nTitle: {title}\nSummary: {summary}\n"

    # HOOK-ALLOW: silent-swallow rationale=SWI-390; exception is captured as a
    # typed Stage1Error sentinel and surfaced via stage1_verdict.error.
    try:
        with span("news_relevance_scoring", url=str(article.get("url") or "")):
            result = await run_agent_with_total_timeout(
                agent,
                prompt,
                agent_name="news_relevance",
                deps=AgentDeps(scan_date=None, agent_key="news_relevance"),
                total_timeout_s=float(OUTER_DISABLE_FALLBACK_WALL_S),
                usage_limits=build_usage_limits(config),
            )
        return result.output
    except Exception as exc:
        logger.warning(
            "news_relevance failed url=%s err=%s",
            article.get("url"),
            exc,
            exc_info=True,
        )
        return Stage1Error(error_class=type(exc).__name__, message=str(exc)[:200])


async def score_relevance(
    articles: list[dict], universe_block: str
) -> list[tuple[dict, Stage1Outcome]]:
    """Score every article under ``LLM_LABELING_CONCURRENCY``.

    Returns rows pairing each article with its verdict, ``None`` (shape
    fail), or ``Stage1Error`` (hard failure). Caller is responsible for
    routing + persistence.
    """
    semaphore = asyncio.Semaphore(LLM_LABELING_CONCURRENCY)

    async def _one(article: dict) -> tuple[dict, Stage1Outcome]:
        async with semaphore:
            return article, await score_relevance_one(article, universe_block)

    return await asyncio.gather(*(_one(a) for a in articles))


def verdict_to_jsonb(verdict: Stage1Outcome) -> str:
    """Serialise a verdict for ``articles.stage1_verdict`` JSONB.

    * ``NewsRelevance`` → its Pydantic JSON dump.
    * ``None`` (shape fail) → ``{"shape_fail": true}``.
    * ``Stage1Error`` → ``{"error": "<class>: <truncated msg>"}`` so the
      backfill predicate + post-mortem audits can grep failure classes.
    """
    if verdict is None:
        return json.dumps({"shape_fail": True})
    if isinstance(verdict, Stage1Error):
        return json.dumps({"error": f"{verdict.error_class}: {verdict.message}"})
    return verdict.model_dump_json()


def routes_to_stage_two(verdict: Stage1Outcome) -> bool:
    """Routing rule — Stage 2 sees the article when:

    * Stage 1 says relevant, OR
    * Stage 1 says LOW confidence (recall rescue — the design-challenge
      review's F6), OR
    * Stage 1 returned ``None`` (shape fail; let Stage 2 try).
    * ``Stage1Error`` → False. No ``candidate_entities`` to seed extractor;
      visible via ``stage1_verdict.error`` for audit.
    """
    if isinstance(verdict, Stage1Error):
        return False
    if verdict is None:
        return True
    if verdict.is_vn_relevant:
        return True
    return verdict.relevance_confidence == "LOW"


def select_candidate_entities(verdict: Stage1Outcome) -> list[str]:
    """Extract Stage-2 seed entities from a Stage-1 outcome.

    Returns the verdict's ``candidate_entities`` for ``NewsRelevance``,
    or an empty list for ``None`` (shape-fail) and ``Stage1Error`` — both
    cases reach Stage 2 (or are dropped) without Stage-1-seeded candidates.
    """
    if isinstance(verdict, NewsRelevance):
        return list(verdict.candidate_entities)
    return []


def drop_bucket(verdict: Stage1Outcome) -> str:
    """Bucket a non-routed article for ``stage1_drops.*`` observability.

    Buckets: ``shape_fail``, ``error`` (Stage1Error), ``non_vn``,
    ``off_topic``, ``low_signal``.
    """
    if isinstance(verdict, Stage1Error):
        return "error"
    if verdict is None:
        return "shape_fail"
    reason = (verdict.abstain_reason or "").lower()
    if reason.startswith("us_") or reason.startswith("european_") or "foreign" in reason:
        return "non_vn"
    if "celebrity" in reason or "sports" in reason or "gossip" in reason:
        return "off_topic"
    return "low_signal"


__all__ = [
    "NewsRelevance",
    "Stage1Error",
    "Stage1Outcome",
    "drop_bucket",
    "routes_to_stage_two",
    "score_relevance",
    "score_relevance_one",
    "select_candidate_entities",
    "verdict_to_jsonb",
]
