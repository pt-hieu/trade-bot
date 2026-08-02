"""Article post-INSERT update writers.

``write_article_sentiments``: the single post-INSERT update writer remaining
after the v1 ticker tagger removal (SWI-390). Pulled from ``insert_content.py``
to keep that module under the line cap.
"""

from __future__ import annotations

import logging
from datetime import date

from ..database import get_db

logger = logging.getLogger(__name__)


async def write_article_sentiments(
    scored: list[tuple[str, float | None, str | None]],
    scan_date: date | None = None,
) -> int:
    """Batch-update articles with LLM-scored sentiment + confidence (SWI-103).

    Each row is `(url, sentiment_score | None, confidence | None)`.
    None on either value writes NULL — a partial provider outage degrades
    to "missing data", never a stale legacy score.

    When `scan_date` is provided, the UPDATE is scoped to articles whose
    `search_id` belongs to that scan (live-pipeline use). When None, every
    matching URL is updated regardless of scan (backfill use).
    """
    if not scored:
        return 0

    urls = [url for url, _, _ in scored]
    scores = [s for _, s, _ in scored]
    confidences = [c for _, _, c in scored]

    db = await get_db()
    try:
        if scan_date is None:
            result = await db.execute(
                """
                UPDATE articles a
                SET sentiment_score = u.score,
                    sentiment_confidence = u.conf::sentiment_confidence_enum,
                    sentiment_tickers = COALESCE(a.affected_tickers, a.sentiment_tickers)
                FROM (
                    SELECT * FROM UNNEST($1::text[], $2::float8[], $3::text[])
                    AS t(url, score, conf)
                ) u
                WHERE a.url = u.url
                """,
                urls,
                scores,
                confidences,
            )
        else:
            result = await db.execute(
                """
                UPDATE articles a
                SET sentiment_score = u.score,
                    sentiment_confidence = u.conf::sentiment_confidence_enum,
                    sentiment_tickers = COALESCE(a.affected_tickers, a.sentiment_tickers)
                FROM (
                    SELECT * FROM UNNEST($1::text[], $2::float8[], $3::text[])
                    AS t(url, score, conf)
                ) u
                WHERE a.url = u.url
                  AND a.search_id IN (SELECT id FROM article_searches WHERE scan_date = $4)
                """,
                urls,
                scores,
                confidences,
                scan_date,
            )
        if not result:
            return 0
        return int((result or "UPDATE 0").split()[-1])
    except Exception as e:
        logger.warning("write_article_sentiments failed (n=%d): %s", len(scored), e)
        return 0
