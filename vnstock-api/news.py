"""News endpoint — RSS fetching with direct and vnstock_news Crawler paths."""

import gc
import logging

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("news")

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Sites where we bypass vnstock_news and fetch RSS directly with browser UA.
# vnexpress: package defaults to tin-moi-nhat.rss (general/lifestyle) — must use business feeds.
# cafebiz: package's HTTP client lacks browser UA — RSS returns empty without it.
#
# vietstock: REMOVED from DIRECT_RSS_FEEDS (2026-03-27). RSS endpoints return HTML
# (ASP.NET session auth required), yielding 0 articles. Crawler.get_articles() uses
# Sitemap fallback and returns articles with descriptions. See 97d4537, e60349a.
DIRECT_RSS_FEEDS = {
    "vnexpress": [
        "https://vnexpress.net/rss/kinh-doanh.rss",
        "https://vnexpress.net/rss/bat-dong-san.rss",
    ],
    "cafebiz": [
        "https://cafebiz.vn/rss/cau-chuyen-kinh-doanh.rss",
        "https://cafebiz.vn/rss/vi-mo.rss",
    ],
}


def _parse_rss_item_text(item, tag_name: str) -> str:
    """Extract text from an RSS item's child tag, returning '' if missing."""
    element = item.find(tag_name)
    if element and element.text:
        return element.text.strip()
    return ""


def fetch_rss_direct(
    feed_urls: list[str],
    site_name: str,
    limit_per_feed: int = 20,
) -> tuple[list[dict], list[str]]:
    """Fetch RSS feeds directly with browser UA — bypasses vnstock_news.

    Returns:
        (articles, failed_urls) — articles list and any URLs that failed.
    """
    articles = []
    failed_urls = []

    for url in feed_urls:
        remaining = limit_per_feed - len(articles)
        if remaining <= 0:
            break
        try:
            response = requests.get(
                url,
                headers={"User-Agent": BROWSER_USER_AGENT},
                timeout=15,
            )
            response.raise_for_status()

            # Guard against sites returning HTML instead of RSS/XML (e.g. auth walls)
            content_type = response.headers.get("content-type", "")
            if "html" in content_type and "xml" not in content_type:
                logger.warning(
                    "RSS %s returned HTML (content-type: %s), skipping", url, content_type[:80]
                )
                failed_urls.append(url)
                continue

            soup = BeautifulSoup(response.content, "xml")

            count_before = len(articles)
            for item in soup.find_all("item")[:remaining]:
                description_html = _parse_rss_item_text(item, "description")
                description_text = (
                    BeautifulSoup(description_html, "html.parser").get_text().strip()
                    if description_html
                    else ""
                )
                articles.append(
                    {
                        "title": _parse_rss_item_text(item, "title"),
                        "url": _parse_rss_item_text(item, "link"),
                        "short_description": description_text,
                        "description": description_text,
                        "publish_time": _parse_rss_item_text(item, "pubDate"),
                        "site": site_name,
                    }
                )
            if len(articles) == count_before:
                logger.warning("RSS %s: 0 items parsed (possible auth wall or empty feed)", url)
        except Exception as error:
            logger.warning("RSS direct fetch failed for %s: %s", url, error)
            failed_urls.append(url)

    return articles, failed_urls


def _fetch_via_crawler(site_name: str, limit: int) -> tuple[list[dict], list[str]]:
    """Fetch articles via vnstock_news Crawler.

    Uses get_articles() which auto-prioritizes RSS, falls back to Sitemap.
    This is critical for vietstock — its RSS returns empty descriptions,
    but Sitemap path returns full descriptions (159-423 chars).
    See: e60349a (RSS empty descriptions), 97d4537 (DIRECT_RSS failed too).
    """
    from vnstock_news import Crawler

    try:
        crawler = Crawler(site_name=site_name)

        raw_articles = crawler.get_articles(limit=limit)

        articles = []
        for article in raw_articles:
            # Normalize field names to match our expected format
            publish_time = article.get("publish_time")
            if publish_time and hasattr(publish_time, "isoformat"):
                publish_time = publish_time.isoformat()
            articles.append(
                {
                    "title": article.get("title") or "",
                    "url": article.get("url") or "",
                    "short_description": article.get("description") or "",
                    "description": article.get("description") or "",
                    "publish_time": publish_time,
                    "site": site_name,
                }
            )

        return articles, []
    except Exception as error:
        logger.warning("Crawler fetch failed for %s: %s", site_name, error)
        return [], [site_name]


def _deduplicate_by_url(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles by URL within a single fetch."""
    seen_urls = set()
    unique_articles = []
    for article in articles:
        url = article.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_articles.append(article)
    return unique_articles


def news_articles(
    sites: str = "cafebiz,vietstock,vnexpress,vneconomy,baodautu",
    limit: int = 20,
    x_api_key: str | None = None,
    verify_api_key_fn=None,
):
    """Fetch latest articles from Vietnamese news RSS feeds.

    Uses direct RSS fetching (with browser UA) for sites in DIRECT_RSS_FEEDS,
    falls back to vnstock_news Crawler for others.
    """
    if verify_api_key_fn:
        verify_api_key_fn(x_api_key)

    site_list = [site.strip() for site in sites.split(",") if site.strip()]
    all_articles = []
    failed_sites = []

    for site_name in site_list:
        if site_name in DIRECT_RSS_FEEDS:
            articles, failed_urls = fetch_rss_direct(DIRECT_RSS_FEEDS[site_name], site_name, limit)
            if failed_urls:
                failed_sites.append(site_name)
        else:
            articles, site_failures = _fetch_via_crawler(site_name, limit)
            failed_sites.extend(site_failures)

        all_articles.extend(articles)

    gc.collect()
    unique_articles = _deduplicate_by_url(all_articles)

    return {
        "articles": unique_articles,
        "count": len(unique_articles),
        "sites": site_list,
        "failed_sites": failed_sites,
    }
