"""
Article search orchestrator.

Fetches Vietnamese + international articles in parallel.
LLM scores relevance and summarizes content (VN only — intl uses RSS descriptions).
"""

import asyncio
import logging
from datetime import date
from pathlib import Path

from data.articles_intl import fetch_international_articles
from data.articles_vn import fetch_vietnamese_articles
from shared.database import get_db

logger = logging.getLogger(__name__)


async def search_articles(
    watchlist: dict,
    holdings: list,
    output_dir: Path,
) -> dict:
    """Search for articles via Vietnamese RSS + international RSS feeds.

    Fetches both sources in parallel. Either can fail independently.
    """
    vn_result, intl_result = await asyncio.gather(
        fetch_vietnamese_articles(watchlist, holdings, output_dir),
        fetch_international_articles(output_dir),
        return_exceptions=True,
    )

    merged: dict = {}

    if isinstance(vn_result, dict):
        merged.update(vn_result)
    else:
        logger.warning("Vietnamese article fetch failed: %s", vn_result)

    if isinstance(intl_result, dict):
        merged.update(intl_result)
    else:
        logger.warning("International article fetch failed: %s", intl_result)

    return merged


async def articles_exist_in_db(
    scan_date: date, query_prefix: str | None = None, min_count: int = 5
) -> bool:
    """Check if articles already exist in DB for this scan date.

    Args:
        scan_date: Date to check.
        query_prefix: If set, only count articles with matching query_name prefix.
            Use "rss-intl-" for international, "rss-" for Vietnamese.
        min_count: Minimum article count to consider "exists".
    """
    db = await get_db()

    if query_prefix:
        row = await db.fetch_one(
            """
            SELECT COUNT(*) as cnt FROM articles a
            JOIN article_searches ars ON ars.id = a.search_id
            WHERE ars.scan_date = $1 AND ars.query_name LIKE $2
            """,
            scan_date,
            f"{query_prefix}%",
        )
    else:
        row = await db.fetch_one(
            """
            SELECT COUNT(*) as cnt FROM articles a
            JOIN article_searches ars ON ars.id = a.search_id
            WHERE ars.scan_date = $1
            """,
            scan_date,
        )

    return (row["cnt"] if row else 0) >= min_count
