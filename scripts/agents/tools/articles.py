#!/usr/bin/env python3
"""
Article tools for searching and reading pre-loaded news articles.

Uses Neon database for article queries. All functions are async.
Tools (tool_*) return prose strings for LLM agents.
Async functions (*_async) return dicts for Python code.
"""

import asyncio
import re
from datetime import date

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

ARTICLE_CONTENT_MAX_CHARS = 3000


def _truncate_text(text: str, limit: int = ARTICLE_CONTENT_MAX_CHARS) -> str:
    """Truncate text to limit with a marker showing original length."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[...truncated, {len(text):,} chars total]"


# ============================================================================
# Prose Formatters - Convert list/dict data to natural language strings
# ============================================================================


def _format_article_list_prose(articles: list[dict]) -> str:
    """Convert article list to natural prose."""
    if not articles:
        return "No articles found."

    if "error" in articles[0]:
        return f"Articles: {articles[0]['error']}"

    parts = [f"Available Articles ({len(articles)} found):"]

    for article in articles[:10]:  # Limit to 10 for readability
        aid = article.get("id", "?")
        title = article.get("title", "Untitled")
        source = article.get("source", "Unknown")
        published_at = article.get("published_at") or ""
        date_str = f" ({published_at[:10]})" if published_at else ""
        parts.append(f'[{aid}] "{title}" - {source}{date_str}')

    if len(articles) > 10:
        parts.append(f"... and {len(articles) - 10} more.")

    return " ".join(parts)


def _format_search_results_prose(articles: list[dict], query: str) -> str:
    """Convert search results to natural prose."""
    if not articles:
        return f'Article Search "{query}": No matches found.'

    if "error" in articles[0]:
        return f'Article Search "{query}": {articles[0]["error"]}'

    parts = [f'Article Search "{query}" ({len(articles)} matches):']

    for article in articles:
        aid = article.get("id", "?")
        title = article.get("title", "Untitled")
        snippet = article.get("snippet", "")
        published_at = article.get("published_at") or ""
        # Truncate snippet to ~60 chars
        if snippet and len(snippet) > 60:
            snippet = snippet[:57] + "..."
        line = f'[{aid}] "{title}"'
        if published_at:
            line += f" ({published_at[:10]})"
        if snippet:
            line += f" - {snippet}"
        parts.append(line)

    return " ".join(parts)


# ============================================================================
# Async Functions for PydanticAI Agents
# ============================================================================


async def list_articles_async(scan_date: date | None = None) -> dict:
    """List available articles - async version for PydanticAI agents.

    Args:
        scan_date: Date of the scan (defaults to today)

    Returns:
        Dict with 'articles' list and 'prose' summary.
        Use result["prose"] for natural language description.
    """
    from shared.neon import list_articles as neon_list_articles

    if scan_date is None:
        scan_date = date.today()

    try:
        articles = await neon_list_articles(scan_date)
        return {
            "articles": articles,
            "prose": _format_article_list_prose(articles),
        }
    except Exception as e:
        return {
            "articles": [],
            "error": f"Failed to list articles: {e}",
            "prose": f"Articles: Failed to list - {e}",
        }


async def search_articles_async(query: str, limit: int = 5, scan_date: date | None = None) -> dict:
    """Search articles by keyword - async version for PydanticAI agents.

    Args:
        query: Search keyword(s)
        limit: Maximum results to return
        scan_date: Date of the scan (defaults to today)

    Returns:
        Dict with 'articles' list and 'prose' summary.
        Use result["prose"] for natural language description.
    """
    from shared.neon import search_articles as neon_search_articles

    if scan_date is None:
        scan_date = date.today()

    try:
        articles = await neon_search_articles(query, limit, scan_date)
        return {
            "articles": articles,
            "prose": _format_search_results_prose(articles, query),
        }
    except Exception as e:
        return {
            "articles": [],
            "error": f"Failed to search articles: {e}",
            "prose": f'Article Search "{query}": Failed - {e}',
        }


async def read_article_async(article_id: str) -> str:
    """Read article content by ID - async version for PydanticAI agents.

    Args:
        article_id: Article UUID from database

    Returns:
        Formatted article content
    """
    from shared.neon import read_article as neon_read_article

    try:
        article = await neon_read_article(article_id)

        if "error" in article:
            return article["error"]

        # Format article for display
        result = f"# {article['title']}\n\n"
        result += f"**Source:** {article['source']}\n"
        result += f"**URL:** {article['url']}\n"
        result += f"**Query:** {article['query']}\n\n"

        if article.get("content"):
            result += "## Content\n\n"
            result += _truncate_text(article["content"])
        elif article.get("summary"):
            result += "## Summary\n\n"
            result += _truncate_text(article["summary"])

        return result
    except Exception as e:
        return f"Failed to read article: {e}"


# ============================================================================
# Agent Tool Functions - Return string for LLM agents
# ============================================================================


async def tool_list_articles(scan_date: date | None = None) -> str:
    """List all available news articles.

    For filtered results use tool_search_articles or tool_list_articles_by_ticker.

    Args:
        scan_date: Date of the scan (defaults to today)

    For use by LLM agents. Returns natural prose string.
    """
    result = await list_articles_async(scan_date)
    return result.get("prose", str(result))


_EN_TO_VI = {
    "foreign flow": "khối ngoại",
    "banking": "ngân hàng",
    "credit": "tín dụng",
    "bad debt": "nợ xấu",
    "interest rate": "lãi suất",
    "real estate": "bất động sản",
    "technology": "công nghệ",
    "steel": "thép",
    "retail": "bán lẻ",
    "consumer": "tiêu dùng",
    "energy": "năng lượng",
    "power": "điện",
    "oil": "dầu khí",
    "insurance": "bảo hiểm",
    "securities": "chứng khoán",
    "market": "thị trường",
    "earnings": "lợi nhuận",
    "dividend": "cổ tức",
    "state owned": "nhà nước",
}


def _translate_query(query: str) -> str:
    """Translate common English terms to Vietnamese for article search."""
    original = query.lower()
    translated = original
    for en, vi in _EN_TO_VI.items():
        if en in translated:
            translated = translated.replace(en, vi)
    return translated if translated != original else query


_TICKER_RE_SEARCH = re.compile(r"\b[A-Z]{2,4}\b")


async def tool_search_articles(query: str, limit: int = 5, scan_date: date | None = None) -> str:
    """Search articles by keyword.

    Args:
        query: Search keyword(s)
        limit: Maximum results to return
        scan_date: Date of the scan (defaults to today)

    For use by LLM agents. Returns natural prose string.
    """
    result = await search_articles_async(query, limit, scan_date)

    # Fallback 1: retry with Vietnamese translation if no results
    if not result.get("articles"):
        translated = _translate_query(query)
        if translated != query:
            result = await search_articles_async(translated, limit, scan_date)

    # Fallback 2: if query contains tickers, try ticker-based search (parallel)
    if not result.get("articles"):
        tickers = _TICKER_RE_SEARCH.findall(query)
        if tickers:
            ticker_results = await asyncio.gather(
                *(list_articles_by_ticker_async(t, scan_date) for t in tickers[:3])
            )
            combined = []
            seen = set()
            for ticker_result in ticker_results:
                for a in ticker_result.get("articles", []):
                    if a["id"] not in seen:
                        seen.add(a["id"])
                        combined.append(a)
            if combined:
                result = {
                    "articles": combined[:limit],
                    "prose": _format_search_results_prose(combined[:limit], query),
                }

    return result.get("prose", str(result))


async def tool_read_article(article_id: str) -> str:
    """Read article content by UUID.

    Args:
        article_id: Article UUID from tool_list_articles (e.g. 'd11d4aaa-0513-449d-a9c2-0b93f7fdc27d')

    For use by LLM agents. Returns natural prose string.
    """
    if not isinstance(article_id, str) or not _UUID_RE.match(article_id):
        return (
            f"Invalid article_id: {article_id}. "
            "Use the UUID from tool_list_articles (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)."
        )
    return await read_article_async(article_id)


async def list_articles_by_ticker_async(ticker: str, scan_date: date | None = None) -> dict:
    """List articles mentioning a specific ticker - async internal function.

    Args:
        ticker: Stock ticker to search for (e.g., 'FOX', 'TCB')
        scan_date: Date of the scan (defaults to today)

    Returns:
        Dict with 'articles' list and 'prose' summary.
    """
    from shared.neon import list_articles_by_ticker as neon_list_by_ticker

    if scan_date is None:
        scan_date = date.today()

    try:
        articles = await neon_list_by_ticker(ticker, scan_date)
        prose = _format_search_results_prose(articles, f"ticker:{ticker}")
        return {"articles": articles, "prose": prose}
    except Exception as e:
        return {"articles": [], "prose": f"Failed to find articles for {ticker}: {e}"}


async def tool_list_articles_by_ticker(ticker: str, scan_date: date | None = None) -> str:
    """List articles mentioning a specific stock ticker.

    Args:
        ticker: Stock ticker to search for (e.g., 'FOX', 'TCB')
        scan_date: Date of the scan (defaults to today)

    For use by LLM agents. Returns natural prose string.
    """
    result = await list_articles_by_ticker_async(ticker, scan_date)
    return result.get("prose", str(result))
