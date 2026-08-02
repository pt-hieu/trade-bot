"""Article queries (list, search, read)."""

import re
from datetime import date, timedelta

from ..database import get_db

_TICKER_RE = re.compile(r"^[A-Z]{2,4}$", re.I)


def _date_range(scan_date: date | None, days: int = 7) -> tuple[date, date, bool]:
    """Return (start, end, is_range) for article queries.

    Uses configurable lookback window ending on scan_date (or today).
    """
    end = scan_date if scan_date is not None else date.today()
    start = end - timedelta(days=days)
    return start, end, True


async def get_issued_query_names(scan_date: date) -> list[str]:
    """Return the distinct ``query_name`` values searched on ``scan_date`` (SWI-389).

    Lets the news-ingest audit diff the queries that actually ran against the
    active watchlist, surfacing tickers that never had a search issued (the
    zero-ingest starvation behind HCM/POW/SAB/DCM/NT2). Empty list when no
    searches were recorded for the date.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """SELECT DISTINCT query_name
             FROM article_searches
            WHERE scan_date = $1
              AND query_name IS NOT NULL
            ORDER BY query_name""",
        scan_date,
    )
    return [row["query_name"] for row in rows]


async def load_articles_for_scan_date(scan_date: date) -> list[dict]:
    """Rehydrate articles for ``scan_date`` as a flat id-bearing list.

    Each row carries the DB ``id`` so Stage 1 verdict + Stage 2 extraction
    UPDATEs can target the correct article. Shape matches the
    ``RehydratedArticle`` TypedDict in ``pipeline.types``.

    Commit-semantics contract: assumes ``insert_articles`` has committed
    before this runs. Do NOT call inside an outer ``async with
    db.transaction()`` — the SELECT may land on a different pool connection
    and miss uncommitted rows.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """SELECT a.id::text AS id,
                  a.url,
                  a.title,
                  a.summary,
                  a.domain,
                  a.summary_length,
                  a.search_description AS description,
                  a.published_at,
                  ars.query_name
             FROM articles a
             JOIN article_searches ars ON ars.id = a.search_id
            WHERE ars.scan_date = $1
            ORDER BY a.published_at DESC NULLS LAST""",
        scan_date,
    )
    return [dict(row) for row in rows]


async def list_articles(scan_date: date | None = None) -> list[dict]:
    """List recent articles (last 7 days from scan_date)."""
    start, end, is_range = _date_range(scan_date)
    date_clause = (
        "ars.scan_date >= $1 AND ars.scan_date <= $2" if is_range else "ars.scan_date = $1"
    )

    db = await get_db()
    date_params = [start, end] if is_range else [start]

    rows = await db.fetch_all(
        f"""
        SELECT * FROM (
            SELECT DISTINCT ON (a.url)
                   a.id, a.title, a.url, a.domain, a.published_at, ars.query_name
            FROM articles a
            JOIN article_searches ars ON ars.id = a.search_id
            WHERE {date_clause}
            ORDER BY a.url, ars.scan_date DESC, a.created_at DESC
        ) deduped
        ORDER BY deduped.title
    """,
        *date_params,
    )

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "source": row["domain"],
            "published_at": str(published_at)
            if (published_at := row.get("published_at"))
            else None,
            "query": row["query_name"],
        }
        for row in rows
    ]


async def list_articles_range(start_date: date, end_date: date) -> list[dict]:
    """List all articles within a date range (inclusive)."""
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT * FROM (
            SELECT DISTINCT ON (a.url)
                   a.id, a.title, a.url, a.domain, a.summary, a.published_at,
                   a.sentiment_score, a.affected_tickers, ars.query_name, ars.scan_date
            FROM articles a
            JOIN article_searches ars ON ars.id = a.search_id
            WHERE ars.scan_date >= $1 AND ars.scan_date <= $2
            ORDER BY a.url, ars.scan_date DESC, a.created_at DESC
        ) deduped
        ORDER BY deduped.scan_date DESC, deduped.title
    """,
        start_date,
        end_date,
    )

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "source": row["domain"],
            "published_at": str(published_at)
            if (published_at := row.get("published_at"))
            else None,
            "query": row["query_name"],
            "summary": row["summary"] or "",
            "sentiment_score": row.get("sentiment_score"),
            "affected_tickers": row.get("affected_tickers") or [],
            "date": str(row["scan_date"]),
        }
        for row in rows
    ]


async def search_articles(query: str, limit: int = 5, scan_date: date | None = None) -> list[dict]:
    """Search articles by keyword with ticker-aware ranking.

    LIKE conditions are AND-joined (all words must appear for text match).
    Ticker conditions are OR-joined (any ticker match is sufficient).
    Results ranked: direct ticker matches first, then text matches.
    When scan_date is None, searches last 7 days.
    """
    start, end, is_range = _date_range(scan_date)
    date_clause = (
        "ars.scan_date >= $1 AND ars.scan_date <= $2" if is_range else "ars.scan_date = $1"
    )

    db = await get_db()
    date_params = list([start, end] if is_range else [start])

    # Split query into individual keywords (min 2 chars)
    words = [w.lower() for w in query.split() if len(w) >= 2]
    if not words:
        words = [query.lower()]

    # Searchable blob: title + summary + description
    searchable = (
        "LOWER(COALESCE(a.title,'') || ' ' || COALESCE(a.summary,'') "
        "|| ' ' || COALESCE(a.search_description,''))"
    )

    # Build word LIKE conditions (AND-joined) + ticker array conditions (OR-joined)
    params: list[date | str | int] = list(date_params)
    like_conditions = []
    ticker_conditions = []
    ticker_rank_cases = []

    for word in words:
        params.append(f"%{word}%")
        idx = len(params)
        like_conditions.append(f"{searchable} LIKE ${idx}")

    # Match ticker-like words against affected_tickers array
    for word in query.split():
        if _TICKER_RE.match(word):
            params.append(word.upper())
            idx = len(params)
            ticker_conditions.append(f"${idx} = ANY(a.affected_tickers)")
            ticker_rank_cases.append(
                f"CASE WHEN ${idx} = ANY(a.affected_tickers) THEN 1 ELSE 0 END"
            )

    # AND-join LIKE (all words must match for text relevance)
    # OR-join tickers (any ticker match is sufficient)
    like_clause = " AND ".join(like_conditions) if like_conditions else None
    ticker_clause = " OR ".join(ticker_conditions) if ticker_conditions else None

    if like_clause and ticker_clause:
        where_clause = f"({like_clause}) OR ({ticker_clause})"
    elif ticker_clause:
        where_clause = ticker_clause
    elif like_clause:
        where_clause = like_clause
    else:
        where_clause = "FALSE"

    # Rank: direct ticker matches first, then by date
    rank_expr = " + ".join(ticker_rank_cases) if ticker_rank_cases else "0::int"

    params.append(limit)
    limit_idx = len(params)

    rows = await db.fetch_all(
        f"""
        WITH deduped AS (
            SELECT DISTINCT ON (a.url)
                   a.id, a.title, a.url, a.domain, a.summary, a.published_at,
                   a.search_description, a.affected_tickers, ars.query_name, ars.scan_date
            FROM articles a
            JOIN article_searches ars ON ars.id = a.search_id
            WHERE {date_clause}
            ORDER BY a.url, ars.scan_date DESC, a.created_at DESC
        )
        SELECT d.id, d.title, d.url, d.domain, d.summary, d.published_at, d.query_name
        FROM deduped d
        WHERE {where_clause.replace("a.", "d.").replace("ars.", "d.")}
        ORDER BY ({rank_expr.replace("a.", "d.")}) DESC, d.scan_date DESC, d.title
        LIMIT ${limit_idx}
    """,
        *params,
    )

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "source": row["domain"],
            "published_at": str(published_at)
            if (published_at := row.get("published_at"))
            else None,
            "snippet": (row["summary"] or "")[:300],
            "query": row["query_name"],
        }
        for row in rows
    ]


async def list_articles_by_ticker(
    ticker: str, scan_date: date | None = None, limit: int = 10
) -> list[dict]:
    """List articles mentioning a specific ticker via affected_tickers array."""
    start, end, is_range = _date_range(scan_date, days=14)
    date_clause = (
        "ars.scan_date >= $1 AND ars.scan_date <= $2" if is_range else "ars.scan_date = $1"
    )

    db = await get_db()
    date_params = [start, end] if is_range else [start]
    ticker_idx = len(date_params) + 1
    limit_idx = ticker_idx + 1

    rows = await db.fetch_all(
        f"""
        SELECT * FROM (
            SELECT DISTINCT ON (a.url)
                   a.id, a.title, a.url, a.domain, a.summary, a.published_at,
                   a.affected_tickers, ars.query_name, ars.scan_date
            FROM articles a
            JOIN article_searches ars ON ars.id = a.search_id
            WHERE {date_clause}
              AND ${ticker_idx} = ANY(a.affected_tickers)
            ORDER BY a.url, ars.scan_date DESC, a.created_at DESC
        ) deduped
        ORDER BY deduped.scan_date DESC, deduped.title
        LIMIT ${limit_idx}
    """,
        *date_params,
        ticker.upper(),
        limit,
    )

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "source": row["domain"],
            "published_at": str(published_at)
            if (published_at := row.get("published_at"))
            else None,
            "tickers": row["affected_tickers"] or [],
            "snippet": (row["summary"] or "")[:300],
            "query": row["query_name"],
        }
        for row in rows
    ]


async def read_article(article_id: str) -> dict:
    """Read full article content by ID (UUID string)."""
    article_id = str(article_id).strip()
    db = await get_db()
    row = await db.fetch_one(
        """
        SELECT a.title, a.url, a.domain, a.summary, a.search_description,
               a.published_at, ars.query_name
        FROM articles a
        JOIN article_searches ars ON ars.id = a.search_id
        WHERE a.id = $1
    """,
        article_id,
    )

    if not row:
        return {"error": f"Article not found: {article_id}"}

    published_at = row.get("published_at")
    return {
        "title": row["title"],
        "url": row["url"],
        "source": row["domain"],
        "summary": row["summary"],
        "content": row["summary"],
        "raw_description": row["search_description"] or "",
        "published_at": str(published_at) if published_at else None,
        "query": row["query_name"],
    }
