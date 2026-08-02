"""Article domain tools — search, read, sector news."""

import asyncio
import logging

from ..registry import ToolDomain, register_domain_tool

logger = logging.getLogger(__name__)

# SWI-339: the article corpus is Vietnamese-language and matched via diacritic-
# sensitive LIKE (no unaccent). ASCII-transliterated terms ("ngan hang") never
# match "ngân hàng", so these are kept in native Unicode, aligned with the
# sector_news.yaml lexicon (the single source the LLM is told to lead with).
_SECTOR_TERMS = {
    "banking": "ngân hàng tín dụng lãi suất",
    "real_estate": "bất động sản dự án thị trường",
    "technology": "công nghệ phần mềm FPT",
    "state_owned": "doanh nghiệp nhà nước cổ tức",
    "consumer": "tiêu dùng bán lẻ nội địa",
    "infrastructure": "đầu tư công thép xây dựng",
}


def _has_vietnamese_chars(text: str) -> bool:
    """True when `text` carries non-ASCII characters (Vietnamese diacritics)."""
    return any(ord(char) > 127 for char in text)


async def search(queries: list[str], limit: int = 5, *, _ctx: dict) -> str:
    """Search articles by one or more keywords. Pass a list like ['AI FPT', 'banking credit'].

    Returns:
        Prose block per query joined by blank lines. Each block starts
        with "=== Query: {query} ===" followed by titles and snippets of
        up to `limit` matching articles. "Failed - {error}" on failure.
    """
    from ...articles import search_articles_async

    scan_date = _ctx.get("scan_date")

    # SWI-329: the corpus is Vietnamese and matched diacritic-sensitively. When
    # NO query carries Vietnamese characters the search will under-match the
    # body — the LLM emitted only ASCII tokens against the lexicon guidance.
    # Warn (do not reject) so legitimate English coverage hints still run as
    # part of the union-OR query list; the signal surfaces the prompting gap.
    if queries and not any(_has_vietnamese_chars(query) for query in queries):
        logger.warning(
            "ARTICLE_SEARCH_PURE_ASCII: all %d queries are ASCII-only against a "
            "Vietnamese corpus — likely under-matching. queries=%s",
            len(queries),
            queries,
        )

    async def _search_one(query: str) -> str:
        result = await search_articles_async(query=query, limit=limit, scan_date=scan_date)
        prose = result.get("prose") if isinstance(result, dict) else str(result)
        return f"=== Query: {query} ===\n{prose}"

    results = await asyncio.gather(*[_search_one(q) for q in queries])
    return "\n\n".join(results)


async def read(article_id: str) -> str:
    """Read article content by ID. Use the UUID string from search results.

    Returns:
        Plain-text article body (title, date, source, content). Returns
        "Invalid article_id: {id}. Must be a UUID string ..." when the
        id is not UUID-shaped.
    """
    from ...articles import _UUID_RE, read_article_async

    aid = str(article_id).strip()
    if not _UUID_RE.match(aid):
        return (
            f"Invalid article_id: {article_id!r}. "
            "Must be a UUID string (e.g. '3f2504e0-4f89-11d3-9a0c-0305e82c3301')."
        )
    return await read_article_async(article_id=aid)


async def search_sector_news(sectors: list[str], *, _ctx: dict) -> str:
    """Search for sector-specific news. Pass a list like ['banking', 'technology'].

    Returns:
        Prose block per sector joined by blank lines. Each block starts
        with "=== {sector} ===" followed by a natural-language summary
        of up to 3 matching articles.
    """
    from ...articles import search_articles_async

    scan_date = _ctx.get("scan_date")

    async def _search_sector(sector: str) -> str:
        query = _SECTOR_TERMS.get(sector, sector)
        result = await search_articles_async(query=query, limit=3, scan_date=scan_date)
        return f"=== {sector} ===\n{result.get('prose', str(result))}"

    results = await asyncio.gather(*[_search_sector(s) for s in sectors])
    return "\n\n".join(results)


register_domain_tool(
    "article.search",
    ToolDomain.ARTICLE,
    search,
    context_keys=("scan_date",),
    returns_hint="prose per query — titles + snippets",
)
register_domain_tool(
    "article.read",
    ToolDomain.ARTICLE,
    read,
    returns_hint="prose — full article body",
)
register_domain_tool(
    "article.search_sector_news",
    ToolDomain.ARTICLE,
    search_sector_news,
    context_keys=("scan_date",),
    returns_hint="prose per sector — news summaries",
)
