"""Write-side helpers for narrative_tracker: create new narratives + update aggregates.

Split out of ``narrative_tracker`` so the orchestrator module stays under the
350-line cap (CLAUDE.md 'Max 300-350 lines per file'). All call sites go
through ``narrative_tracker`` — this module is an implementation detail.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import date

import numpy as np
from pydantic import ValidationError

from shared.neon.narratives import (
    add_narrative_update,
    update_narrative_on_article,
    upsert_narrative,
)
from shared.rules.narrative_sector_filter import filter_tickers_by_sector
from shared.rules.sentiment_confidence import is_trusted, max_confidence
from shared.vn_universe import filter_vn_only

logger = logging.getLogger(__name__)

JUNK_NARRATIVE_PATTERNS = [
    "lacks content",
    "daily market summary",
    "general news",
    "no specific theme",
    "untitled",
    "empty article",
]


async def create_narrative(article: dict, embedding: list[float], scan_date: date) -> dict | None:
    """LLM labels new narrative, inserts to DB.

    Returns a dict with the freshly-created narrative's id + label metadata
    needed by callers that want to seed an in-memory centroid record
    (``id``, ``narrative_key``, ``narrative_type``, ``affected_tickers``,
    ``affected_sectors``, ``half_life_days``) — or ``None`` on failure.
    """
    summary = article.get("summary") or ""
    title = article.get("title") or ""
    if len(summary) < 30 and len(title) < 10:
        logger.warning(
            "Skipping narrative creation for article %s: insufficient content "
            "(summary=%d chars, title=%d chars)",
            article.get("id"),
            len(summary),
            len(title),
        )
        return None

    try:
        from agents.narrative_labeler import label_narrative

        label = await label_narrative(article, scan_date)

        theme_lower = label.theme.lower()
        if any(pattern in theme_lower for pattern in JUNK_NARRATIVE_PATTERNS):
            logger.info(
                "Rejecting junk narrative label '%s' for article %s",
                label.theme,
                article.get("id"),
            )
            return None

        # SWI-103 R2 RCA F5: only seed avg_sentiment when the seed article's
        # confidence is trusted (high/medium). Otherwise leave NULL so the
        # matching gate's `is_trusted(narrative_confidence)` check
        # short-circuits and the running aggregator skips this contribution.
        seed_conf = article.get("sentiment_confidence")
        seed_score = article.get("sentiment_score")
        seed_avg = float(seed_score) if (is_trusted(seed_conf) and seed_score is not None) else None
        data = {
            "narrative_key": label.narrative_key[:100],
            "theme": label.theme,
            "narrative_type": label.narrative_type,
            "affected_tickers": [t.upper() for t in label.affected_tickers],
            "affected_sectors": label.affected_sectors,
            "article_count": 1,
            "source_count": 1,
            "avg_sentiment": seed_avg,
            "sentiment_confidence_roll": seed_conf,
            "first_seen": scan_date,
            "last_seen": scan_date,
            "conviction_score": 0.2,
            "half_life_days": label.half_life_days,
            "summary": label.theme,
            "trading_implication": label.trading_implication,
            "centroid_embedding": embedding,
            "status": "active",
            "maturity": "emerging",
        }

        narrative_id = await upsert_narrative(data)
        if not narrative_id:
            return None

        await add_narrative_update(
            narrative_id=narrative_id,
            article_id=str(article["id"]),
            update_date=scan_date,
            headline=article.get("title") or "Untitled",
            sentiment_shift="neutral",
        )
        return {
            "id": narrative_id,
            "narrative_key": data["narrative_key"],
            "narrative_type": data["narrative_type"],
            "affected_tickers": data["affected_tickers"],
            "affected_sectors": data["affected_sectors"],
            "half_life_days": data["half_life_days"],
        }

    except (ValidationError, TimeoutError, json.JSONDecodeError) as e:
        # Verified raise set for label_narrative (AUDIT-2026-04-24-001 / ISSUE-2026-04-24-003):
        # - TimeoutError from run_agent_with_total_timeout's asyncio.wait_for
        # - pydantic.ValidationError from structured-output coercion
        # - json.JSONDecodeError from JSON parsing in the agent pipeline
        # DB / network errors propagate to _assign_all_articles' ratio guard.
        logger.warning("Narrative creation failed for article %s: %s", article.get("id"), e)
        return None


async def update_narrative_aggregates(
    narrative_id: str,
    cached_info: dict,
    article: dict,
    embedding: list[float],
    scan_date: date,
    source_count: int,
    *,
    universe: frozenset[str] | None = None,
    sector_map: Mapping[str, str | None] | None = None,
    narrative_type: str | None = None,
    affected_sectors: list[str] | None = None,
) -> None:
    """Update centroid (running average), counts, sentiment, last_seen in single DB call.

    SWI-197 / SWI-200: ``universe`` filters non-VN tickers (UAE/BOJ/etc.)
    before merging into ``narratives.affected_tickers``. ``sector_map``,
    ``narrative_type``, and ``affected_sectors`` are passed when the caller
    wants cross-sector contamination dropped (HPG-Agri narrative no longer
    absorbs TCB/MSN). Both filters are no-ops when their inputs are None.
    """
    old_count = cached_info.get("article_count") or 1
    new_count = old_count + 1

    old_emb = cached_info.get("embedding")
    if old_emb is not None:
        new_centroid = ((old_emb * old_count + np.array(embedding)) / new_count).tolist()
    else:
        new_centroid = embedding

    # SWI-103 R2 RCA F5: only fold trusted articles into avg_sentiment.
    # Untrusted contributions leave the running average untouched. The
    # narrative-level confidence rollup uses max-contributor strategy.
    article_conf = article.get("sentiment_confidence")
    article_score = article.get("sentiment_score")
    old_avg_raw = cached_info.get("avg_sentiment")
    if is_trusted(article_conf) and article_score is not None:
        if old_avg_raw is None:
            new_avg = float(article_score)
        else:
            new_avg = (float(old_avg_raw) * old_count + float(article_score)) / new_count
    else:
        new_avg = old_avg_raw  # may stay None
    new_conf_roll = max_confidence([cached_info.get("sentiment_confidence_roll"), article_conf])

    # Fix 5 (2026-04-21): feed the matched article's tickers through so the
    # narrative's affected_tickers keeps expanding as more articles attach.
    # Previously mature narratives with 17 articles could still show
    # affected_tickers=[]. Sectors aren't passed — the `articles` table has
    # no `affected_sectors` column, so the new_sectors param is left as []
    # pending a future article-schema extension.
    article_tickers_raw = article.get("affected_tickers") or []
    article_tickers = filter_vn_only(
        [str(t) for t in article_tickers_raw],
        universe,
        context=f"narrative_aggregator narrative_id={narrative_id}",
    )
    if narrative_type and sector_map is not None:
        article_tickers = filter_tickers_by_sector(
            article_tickers,
            narrative_type,
            affected_sectors or [],
            sector_map,
        )

    await update_narrative_on_article(
        narrative_id=narrative_id,
        new_embedding=new_centroid,
        article_count=new_count,
        source_count=source_count,
        avg_sentiment=new_avg,
        last_seen=scan_date,
        new_tickers=article_tickers,
        sentiment_confidence_roll=new_conf_roll,
    )

    # Side-effect: update in-memory cache so subsequent matched articles see fresh centroids
    cached_info["embedding"] = np.array(new_centroid)
    cached_info["article_count"] = new_count
    cached_info["source_count"] = source_count
    cached_info["avg_sentiment"] = new_avg
    cached_info["sentiment_confidence_roll"] = new_conf_roll
