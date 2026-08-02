"""Article-search + article INSERT writers.

Splits in this folder:
  * ``insert_content`` (this module) — article search + article inserts.
  * ``insert_midday`` — midday-check writers (override contract +
    child-row verification).
  * ``update_content`` — post-INSERT updaters (tickers, sentiment).

All three keep their public symbols re-exported here so historical import
paths (``from shared.neon.insert_content import insert_midday_check``) keep
working without churn at every call site.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from email.utils import parsedate_to_datetime

from ..database import get_db
from ._sync import make_sync

logger = logging.getLogger(__name__)


def _parse_publish_time(raw: str | None) -> datetime | None:
    """Parse RFC-2822 pubDate or ISO format publish_time to datetime."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            logger.warning("Unparseable publish_time: %s", raw[:80])
            return None


async def insert_articles(scan_date: date, search_results: dict) -> tuple[int, list[str]]:
    """Insert article search results and articles.

    Returns:
        (count, failed_sites) — queries inserted and list of site names that failed.
    """
    db = await get_db()
    count = 0
    failed_sites: list[str] = []

    # affected_tickers is written exclusively by news_v2_persist after Stage-2
    # LLM extraction (SWI-390). The INSERT-time baseline substring matcher and
    # its VN-universe priming were deleted with the v1 orchestrator residue —
    # the matcher was tagging Ru-SSI-a, g-REE-n via substring collisions. The
    # earlier SWI-197 baseline guarantee is intentionally withdrawn here:
    # missing data is preferred over false positives.

    for query_name, query_data in search_results.items():
        query_text = query_data.get("query", query_name)
        status = query_data.get("status", "success")
        articles_list = query_data.get("articles", [])
        skipped = query_data.get("skipped", 0)

        try:
            async with db.transaction() as conn:
                search_id = await conn.fetchval(
                    """
                    INSERT INTO article_searches (scan_date, query_name, query_text, status, article_count, skipped_count)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (scan_date, query_name) DO UPDATE SET
                        query_text = EXCLUDED.query_text, status = EXCLUDED.status,
                        article_count = EXCLUDED.article_count, skipped_count = EXCLUDED.skipped_count
                    RETURNING id
                    """,
                    scan_date,
                    query_name,
                    query_text,
                    status,
                    len(articles_list),
                    skipped,
                )

                fallback_published_at = datetime.combine(scan_date, datetime.min.time())
                rows = []
                tickers: list[str] = []
                for article in articles_list:
                    published_at = (
                        _parse_publish_time(article.get("publish_time")) or fallback_published_at
                    )
                    rows.append(
                        (
                            search_id,
                            article.get("title") or "",
                            article.get("url", ""),
                            article.get("domain"),
                            article.get("summary"),
                            article.get("summary_length"),
                            article.get("description"),
                            article.get("file_path"),
                            tickers,
                            published_at,
                        )
                    )

                if rows:
                    await conn.executemany(
                        """
                        INSERT INTO articles (search_id, title, url, domain, summary, summary_length,
                            search_description, file_path, affected_tickers, published_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (url, search_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            summary = EXCLUDED.summary,
                            summary_length = EXCLUDED.summary_length,
                            search_description = EXCLUDED.search_description,
                            -- affected_tickers intentionally NOT updated — written only by news_v2_persist (SWI-390); re-ingest of the same (url, search_id) preserves Stage-2 output.
                            published_at = EXCLUDED.published_at
                        """,
                        rows,
                    )

            count += 1
        except Exception as e:
            logger.warning("Failed to insert articles for %s: %s", query_name, e)
            failed_sites.append(query_name)

    return count, failed_sites


# Re-export sibling writers so historical import paths keep working.
from .insert_midday import insert_midday_check, insert_midday_check_sync  # noqa: E402
from .update_content import write_article_sentiments  # noqa: E402

insert_articles_sync = make_sync(insert_articles)


__all__ = (
    "insert_articles",
    "insert_articles_sync",
    "insert_midday_check",
    "insert_midday_check_sync",
    "write_article_sentiments",
)
