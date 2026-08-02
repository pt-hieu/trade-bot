"""International article pipeline via RSS feeds.

Pipeline:
1. Fetch RSS feeds in parallel via httpx + xml.etree.ElementTree
2. Normalize entries to common article format
3. Deduplicate by URL + title similarity (cross-domain wire dedup)
4. Pre-filter (English blocklist + macro keyword allowlist + age)
5. LLM relevance scoring (macro/geopolitical focus — no summarization)
6. Return search_results dict for DB insertion

Module layout (post-modularisation, SWI-212):
  * ``feeds.py`` — INTL_FEEDS catalog, RSS parser, parallel fetcher.
  * ``filtering.py`` — blocklist + macro allowlist + Jaccard title dedup.
  * ``scoring.py`` — LLM relevance scoring (batched).
  * ``__init__.py`` — fetch_international_articles entry point + re-exports.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from pathlib import Path

from ..articles_vn import deduplicate_by_url, extract_domain
from .feeds import INTL_FEEDS, _is_stale, _parse_published, fetch_all_feeds
from .filtering import intl_pre_filter, title_dedup
from .scoring import _score_intl_relevance

INTL_QUERY_PREFIX = "rss-intl-"

logger = logging.getLogger(__name__)


async def fetch_international_articles(
    output_dir: Path,
    min_score: int = 5,
) -> dict:
    """Fetch and process international RSS articles.

    Returns search_results dict matching insert_articles() format.
    Lower min_score (5 vs 6 for VN) — macro articles score lower on VN relevance.
    No LLM summarization — RSS descriptions stored directly as summaries.
    """
    print("Fetching international articles via RSS...")

    all_articles, failed_slugs = await fetch_all_feeds()
    print(
        f"  Fetched {len(all_articles)} articles from {len(INTL_FEEDS) - len(failed_slugs)}/{len(INTL_FEEDS)} feeds"
    )
    if failed_slugs:
        print(f"  Failed feeds: {', '.join(failed_slugs)}")

    unique = deduplicate_by_url(all_articles)

    filtered = intl_pre_filter(unique)
    print(f"  {len(filtered)}/{len(unique)} passed pre-filter (blocklist + allowlist + age)")

    deduped = title_dedup(filtered)
    if len(deduped) < len(filtered):
        print(f"  {len(filtered) - len(deduped)} wire duplicates removed")

    if not deduped:
        print("  No articles after filtering — skipping scoring")
        return {}

    print(f"  Scoring {len(deduped)} articles for macro relevance...")
    scores = await asyncio.to_thread(_score_intl_relevance, deduped, min_score)

    relevant = [(i, article) for i, article in enumerate(deduped) if scores.get(i, 0) >= min_score]
    print(
        f"  {len(relevant)} relevant (score >= {min_score}), {len(deduped) - len(relevant)} skipped"
    )

    search_results: dict = {}
    for _idx, article in relevant:
        site = article.get("site", "unknown")
        query_name = f"{INTL_QUERY_PREFIX}{site}"
        domain = extract_domain(article.get("url", ""))
        summary = (article.get("short_description") or "")[:500]

        if query_name not in search_results:
            search_results[query_name] = {
                "query": f"RSS feed: {domain or site}",
                "status": "success",
                "count": 0,
                "skipped": 0,
                "articles": [],
            }
        search_results[query_name]["articles"].append(
            {
                "title": article.get("title") or "",
                "url": article.get("url", ""),
                "source": domain,
                "domain": domain,
                "summary": summary,
                "summary_length": len(summary),
                "description": summary,
                "publish_time": article.get("publish_time"),
            }
        )
        search_results[query_name]["count"] += 1

    site_totals = Counter(article.get("site") for article in deduped)
    for query_name in search_results:
        slug = query_name.replace(INTL_QUERY_PREFIX, "")
        search_results[query_name]["skipped"] = (
            site_totals.get(slug, 0) - search_results[query_name]["count"]
        )

    total = sum(result["count"] for result in search_results.values())
    print(f"  Processed {total} relevant international articles")

    output_file = output_dir / "search-results-intl.json"
    with open(output_file, "w", encoding="utf-8") as file_handle:
        json.dump(search_results, file_handle, indent=2, ensure_ascii=False)

    return search_results


__all__ = [
    "INTL_FEEDS",
    "INTL_QUERY_PREFIX",
    "_is_stale",
    "_parse_published",
    "fetch_all_feeds",
    "fetch_international_articles",
    "intl_pre_filter",
    "title_dedup",
]
