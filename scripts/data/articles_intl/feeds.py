"""International RSS feed catalog + parallel-fetch + parse helpers."""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

INTL_FEEDS: list[dict[str, str]] = [
    {
        "slug": "cnbc-economy",
        "name": "CNBC Economy",
        "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
        "category": "macro",
    },
    {
        "slug": "marketwatch",
        "name": "MarketWatch",
        "url": "http://feeds.marketwatch.com/marketwatch/topstories/",
        "category": "macro",
    },
    {
        "slug": "oilprice",
        "name": "OilPrice.com",
        "url": "https://oilprice.com/rss/main",
        "category": "commodities",
    },
    {
        "slug": "fed-press",
        "name": "Federal Reserve",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "category": "monetary",
    },
    {
        "slug": "ecb-press",
        "name": "ECB",
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "category": "monetary",
    },
    {
        "slug": "nikkei-asia",
        "name": "Nikkei Asia",
        "url": "https://asia.nikkei.com/rss/feed/nar",
        "category": "asia",
    },
    {
        "slug": "vnexpress-intl",
        "name": "VnExpress English",
        "url": "https://e.vnexpress.net/rss/business.rss",
        "category": "vietnam",
    },
]

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_MAX_ARTICLE_AGE = timedelta(hours=36)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DC_NS = "{http://purl.org/dc/elements/1.1/}"
_RDF_NS = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_RSS1_NS = "{http://purl.org/rss/1.0/}"


def _parse_published(text: str | None) -> str | None:
    """Parse RSS pubDate (RFC 822) or dc:date (ISO 8601) to ISO string."""
    if not text or not text.strip():
        return None
    text = text.strip()
    try:
        return parsedate_to_datetime(text).isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(text).isoformat()
    except Exception:
        pass
    return None


def _is_stale(publish_time: str | None) -> bool:
    """Return True if article is older than _MAX_ARTICLE_AGE."""
    if not publish_time:
        return False
    try:
        published = datetime.fromisoformat(publish_time)
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        return datetime.now(UTC) - published > _MAX_ARTICLE_AGE
    except Exception:
        return False


def _el_text(item: ET.Element, tag: str) -> str:
    """Extract text from an XML element's child tag (plain + RSS 1.0 NS)."""
    element = item.find(tag)
    if element is None:
        element = item.find(f"{_RSS1_NS}{tag}")
    if element is not None and element.text:
        return element.text.strip()
    return ""


def _strip_html(text: str) -> str:
    """Remove HTML tags from RSS description content."""
    return _HTML_TAG_RE.sub("", text).strip()


async def _fetch_single_feed(
    client: httpx.AsyncClient,
    feed: dict[str, str],
) -> tuple[str, list[dict], str | None]:
    """Fetch and parse a single RSS feed. Returns (slug, articles, error)."""
    slug = feed["slug"]
    try:
        response = await client.get(feed["url"], follow_redirects=True)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "html" in content_type and "xml" not in content_type and "rss" not in content_type:
            return slug, [], f"HTML response (content-type: {content_type[:60]})"

        root = ET.fromstring(response.content)
        articles: list[dict] = []

        items = list(root.iter("item")) or list(root.iter(f"{_RSS1_NS}item"))
        for item in items[:30]:
            description_raw = _el_text(item, "description")
            description_text = _strip_html(description_raw) if description_raw else ""
            pub_text = _el_text(item, "pubDate") or _el_text(item, f"{_DC_NS}date")
            link = _el_text(item, "link") or item.get(f"{_RDF_NS}about", "")
            articles.append(
                {
                    "title": _el_text(item, "title"),
                    "url": link,
                    "short_description": description_text[:500],
                    "publish_time": _parse_published(pub_text),
                    "site": slug,
                    "category": feed["category"],
                }
            )

        if not articles:
            logger.warning("RSS %s: 0 items parsed (empty feed or auth wall)", slug)

        return slug, articles, None

    except httpx.HTTPStatusError as http_error:
        return slug, [], f"HTTP {http_error.response.status_code}"
    except Exception as error:
        return slug, [], str(error)


async def fetch_all_feeds() -> tuple[list[dict], list[str]]:
    """Fetch all international feeds in parallel. Returns (articles, failed_slugs)."""
    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        timeout=httpx.Timeout(30.0),
    ) as client:
        results = await asyncio.gather(
            *[_fetch_single_feed(client, feed) for feed in INTL_FEEDS],
            return_exceptions=True,
        )

    all_articles: list[dict] = []
    failed_slugs: list[str] = []

    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            slug = INTL_FEEDS[i]["slug"]
            logger.warning("Feed %s raised exception: %s", slug, result)
            failed_slugs.append(slug)
            continue
        assert isinstance(result, tuple)
        slug, articles, error = result
        if error:
            logger.warning("Feed %s failed: %s", slug, error)
            failed_slugs.append(slug)
        else:
            logger.info("Feed %s: %d articles", slug, len(articles))
            all_articles.extend(articles)

    if len(failed_slugs) == len(INTL_FEEDS):
        raise RuntimeError("All international RSS feeds failed — check connectivity")

    return all_articles, failed_slugs
