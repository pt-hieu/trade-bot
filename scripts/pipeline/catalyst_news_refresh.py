"""Lightweight intraday news refresh used by catalyst_check.

Extracted from scripts/catalyst_check.py to keep the entry-point under the
350-line cap. No LLM calls — fetches RSS, deterministic filters, DB insert,
then runs the v2 two-stage pass.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from data.articles_intl import INTL_QUERY_PREFIX, fetch_all_feeds, intl_pre_filter, title_dedup
from data.articles_vn import DEFAULT_SITES, deduplicate_by_url, extract_domain, pre_filter
from pipeline.news_v2_persist import run_news_v2_pass
from shared.neon import insert_articles, load_articles_for_scan_date
from shared.telegram import send_telegram_error
from shared.vnstock_client import fetch_news_articles

logger = logging.getLogger(__name__)

_NEWS_REFRESH_TIMEOUT = 180


def _add_to_search_results(search_results: dict, articles: list[dict], prefix: str) -> None:
    """Build search_results dict entries from raw articles."""
    for article in articles:
        site = article.get("site") or "unknown"
        query_name = f"{prefix}{site}"
        url = article.get("url") or ""
        domain = extract_domain(url)
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
                "url": url,
                "source": domain,
                "domain": domain,
                "summary": summary,
                "summary_length": len(summary),
                "description": summary,
                "publish_time": article.get("publish_time") or article.get("lastmod"),
            }
        )
        search_results[query_name]["count"] += 1


async def refresh_news(scan_date: date) -> dict:
    """Lightweight intraday article refresh. No LLM calls.

    Fetches VN + intl RSS, applies deterministic filters, inserts to DB,
    tags tickers, scores sentiment. Bypasses morning pipeline's idempotency gate.
    """
    result = {"vn_count": 0, "intl_count": 0, "sentiment": 0}
    try:
        vn_task = fetch_news_articles(sites=DEFAULT_SITES, limit=20)
        intl_task = fetch_all_feeds()

        vn_raw, (intl_raw, intl_failed) = await asyncio.wait_for(
            asyncio.gather(vn_task, intl_task),
            timeout=_NEWS_REFRESH_TIMEOUT,
        )
        if intl_failed:
            logger.warning("Intl RSS feeds failed: %s", ", ".join(intl_failed))

        vn_unique = pre_filter(deduplicate_by_url(vn_raw))
        intl_filtered = title_dedup(intl_pre_filter(deduplicate_by_url(intl_raw)))

        print(
            f"  News fetch: {len(vn_unique)} VN, {len(intl_filtered)} intl "
            f"(from {len(vn_raw)} + {len(intl_raw)} raw)",
            flush=True,
        )

        search_results: dict = {}
        _add_to_search_results(search_results, vn_unique, prefix="rss-")
        _add_to_search_results(search_results, intl_filtered, prefix=INTL_QUERY_PREFIX)

        if not search_results:
            print("  No articles after filtering", flush=True)
            return result

        inserted, failed_sites = await insert_articles(scan_date, search_results)
        if failed_sites:
            logger.warning("Article insert failed for sites: %s", failed_sites)
        result["vn_count"] = sum(
            r["count"] for qn, r in search_results.items() if not qn.startswith(INTL_QUERY_PREFIX)
        )
        result["intl_count"] = sum(
            r["count"] for qn, r in search_results.items() if qn.startswith(INTL_QUERY_PREFIX)
        )
        print(f"  Inserted {inserted} articles to DB", flush=True)

        # News v2 two-stage pass (replaces tag + sentiment). Rehydrate from
        # the DB so each article carries its UUID — RSS dicts from the fetch
        # path have no id and silently no-op'd Stage 1 verdict UPDATEs.
        rehydrated_articles = await load_articles_for_scan_date(scan_date)
        sentiment_count = await run_news_v2_pass(scan_date, rehydrated_articles)
        result["sentiment"] = sentiment_count
        print(f"  Sentiment scored: {result['sentiment']}", flush=True)

    except TimeoutError:
        logger.warning(
            "News refresh timed out after %ds — continuing with stale data",
            _NEWS_REFRESH_TIMEOUT,
        )
    except Exception as exc:
        # Fail loudly. The previous swallow-and-warn here is what kept the
        # 10-day outage invisible to the operator.
        send_telegram_error(f"News refresh failed: {exc}")
        raise

    return result
