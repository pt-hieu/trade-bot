"""Orchestrator for parallel article sentiment scoring + DB write (SWI-103).

Lives in `agents/` — not `shared/neon/` — to keep the dependency direction
clean (shared/neon never imports agents). The DB writer
`write_article_sentiments` stays in `shared/neon/update_content.py`; this
module batches per-article LLM calls under a shared semaphore and hands
the result list to the writer.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from shared.agent_config import LLM_LABELING_CONCURRENCY
from shared.neon.update_content import write_article_sentiments

from .article_sentiment import score_article_sentiment

logger = logging.getLogger(__name__)


async def score_articles_under_semaphore(
    articles: list[dict],
) -> list[tuple[str, float | None, str | None]]:
    """Run `score_article_sentiment` on each article under a shared semaphore.

    Returns rows in the writer-ready shape (`(url, score, confidence)`) so
    both the live runner and the offline backfill share the same throttle
    + LLM-error handling. Failure / no-input rows surface as
    `(url, None, None)`.
    """
    semaphore = asyncio.Semaphore(LLM_LABELING_CONCURRENCY)

    async def _one(article: dict) -> tuple[str, float | None, str | None]:
        url = article.get("url") or ""
        async with semaphore:
            try:
                result = await score_article_sentiment(article)
            except Exception as exc:
                logger.warning("sentiment LLM failed url=%s: %s", url, exc)
                return url, None, None
        if result is None:
            return url, None, None
        return url, result.sentiment_score, result.confidence

    return await asyncio.gather(*(_one(a) for a in articles))


async def run_article_sentiment_scoring(scan_date: date, search_results: dict) -> int:
    """Score every article with summary via the LLM, then batch-update the DB."""
    articles = [
        article
        for query_data in search_results.values()
        if isinstance(query_data, dict)
        for article in query_data.get("articles", [])
        if article.get("url") and article.get("summary")
    ]
    if not articles:
        return 0

    rows = await score_articles_under_semaphore(articles)
    return await write_article_sentiments(rows, scan_date=scan_date)
