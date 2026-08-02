"""CRUD operations for company_research and longterm_watchlist automation columns."""

import json
from datetime import date

from ..database import get_db
from ._sync import make_sync

# ── company_research ─────────────────────────────────────────────────────────


def _decode_research_row(row) -> dict:
    return {
        "ticker": row["ticker"],
        "sections": row["sections"]
        if isinstance(row["sections"], dict)
        else json.loads(row["sections"]),
        "research_date": str(row["research_date"]),
        "auto_generated": row["auto_generated"],
        "version": row["version"],
        "updated_at": str(row["updated_at"]),
    }


async def get_company_research(ticker: str) -> dict | None:
    """Get research sections for a ticker.

    Returns dict with keys: ticker, sections, research_date, auto_generated, version.
    Returns None if no research exists.
    """
    db = await get_db()
    row = await db.fetch_one(
        """
        SELECT ticker, sections, research_date, auto_generated, version, updated_at
        FROM company_research
        WHERE ticker = $1
        """,
        ticker.upper(),
    )
    if not row:
        return None
    return _decode_research_row(row)


async def get_company_research_batch(tickers: list[str]) -> dict[str, dict | None]:
    """Get research sections for a batch of tickers in one query.

    Returns dict mapping uppercased ticker to research dict or None when absent.
    """
    if not tickers:
        return {}

    normalized = [ticker.upper() for ticker in tickers]
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT ticker, sections, research_date, auto_generated, version, updated_at
        FROM company_research
        WHERE ticker = ANY($1::text[])
        """,
        normalized,
    )
    found: dict[str, dict | None] = {row["ticker"]: _decode_research_row(row) for row in rows}
    return {ticker: found.get(ticker) for ticker in normalized}


async def upsert_company_research(
    ticker: str,
    sections: dict,
    research_date: date | str | None = None,
    auto_generated: bool = True,
) -> None:
    """Upsert company research sections.

    Increments version on update.
    """
    if research_date is None:
        research_date = date.today()
    elif isinstance(research_date, str):
        from datetime import datetime

        research_date = datetime.strptime(research_date, "%Y-%m-%d").date()
    db = await get_db()
    await db.execute(
        """
        INSERT INTO company_research (ticker, sections, research_date, auto_generated, version)
        VALUES ($1, $2::jsonb, $3, $4, 1)
        ON CONFLICT (ticker) DO UPDATE
        SET sections       = EXCLUDED.sections,
            research_date  = EXCLUDED.research_date,
            auto_generated = EXCLUDED.auto_generated,
            version        = company_research.version + 1,
            updated_at     = NOW()
        """,
        ticker.upper(),
        json.dumps(sections),
        research_date,
        auto_generated,
    )


# ── longterm_watchlist automation columns ────────────────────────────────────


async def update_longterm_entry_zone(
    ticker: str,
    entry_zone_vnd: int,
    method: str = "calculated",
) -> None:
    """Update entry zone and method for a longterm watchlist ticker."""
    db = await get_db()
    await db.execute(
        """
        UPDATE longterm_watchlist
        SET entry_zone_vnd   = $2,
            entry_zone_method = $3,
            updated_at        = NOW()
        WHERE ticker = $1
        """,
        ticker.upper(),
        entry_zone_vnd,
        method,
    )


async def update_longterm_conviction(
    ticker: str,
    conviction: str,
    score: int,
    method: str = "calculated",
) -> None:
    """Update conviction level, score, and method."""
    db = await get_db()
    await db.execute(
        """
        UPDATE longterm_watchlist
        SET conviction        = $2::conviction_level,
            conviction_score  = $3,
            conviction_method = $4,
            updated_at        = NOW()
        WHERE ticker = $1
        """,
        ticker.upper(),
        conviction,
        score,
        method,
    )


async def update_longterm_review_flags(ticker: str, flags: list[str]) -> None:
    """Update review_flags array for a ticker."""
    db = await get_db()
    await db.execute(
        """
        UPDATE longterm_watchlist
        SET review_flags    = $2::text[],
            last_reviewed_at = NOW(),
            updated_at       = NOW()
        WHERE ticker = $1
        """,
        ticker.upper(),
        flags,
    )


async def update_longterm_ratios(
    ticker: str,
    pe: float | None,
    roe: float | None,
    div_yield: float | None,
) -> None:
    """Snapshot latest PE, ROE, dividend_yield onto watchlist table."""
    db = await get_db()
    await db.execute(
        """
        UPDATE longterm_watchlist
        SET pe_ratio      = $2,
            roe           = $3,
            dividend_yield = $4,
            updated_at    = NOW()
        WHERE ticker = $1
        """,
        ticker.upper(),
        pe,
        roe,
        div_yield,
    )


async def mark_longterm_reviewed(ticker: str) -> None:
    """Set last_reviewed_at = NOW() without changing other fields."""
    db = await get_db()
    await db.execute(
        "UPDATE longterm_watchlist SET last_reviewed_at = NOW(), updated_at = NOW() WHERE ticker = $1",
        ticker.upper(),
    )


async def add_longterm_stock(
    ticker: str,
    sector: str,
    entry_zone_vnd: int,
    conviction: str,
    tier: int = 2,
    entry_zone_method: str = "llm",
    conviction_method: str = "llm",
) -> bool:
    """Add a new stock to the longterm watchlist.

    Returns True if added, False if sector lookup fails.
    """
    db = await get_db()
    sector_id = await db.fetch_val(
        "SELECT id FROM sectors WHERE LOWER(name) = LOWER($1)",
        sector,
    )
    if not sector_id:
        print(f"  [Neon/longterm] Sector not found: {sector}")
        return False

    await db.execute(
        """
        INSERT INTO longterm_watchlist (
            ticker, sector_id, entry_zone_vnd, conviction, tier,
            entry_zone_method, conviction_method, is_active
        )
        VALUES ($1, $2, $3, $4::conviction_level, $5, $6, $7, TRUE)
        ON CONFLICT (ticker) DO UPDATE
        SET entry_zone_vnd    = EXCLUDED.entry_zone_vnd,
            conviction        = EXCLUDED.conviction,
            entry_zone_method = EXCLUDED.entry_zone_method,
            conviction_method = EXCLUDED.conviction_method,
            is_active         = TRUE,
            updated_at        = NOW()
        """,
        ticker.upper(),
        sector_id,
        entry_zone_vnd,
        conviction,
        tier,
        entry_zone_method,
        conviction_method,
    )
    print(f"  [Neon/longterm] Added {ticker} ({sector}) tier={tier}")
    return True


async def deactivate_longterm_stock(ticker: str) -> bool:
    """Soft-delete a stock from the longterm watchlist (is_active=FALSE)."""
    db = await get_db()
    result = await db.execute(
        "UPDATE longterm_watchlist SET is_active = FALSE, updated_at = NOW() WHERE ticker = $1",
        ticker.upper(),
    )
    success = "UPDATE 0" not in result
    if success:
        print(f"  [Neon/longterm] Deactivated {ticker}")
    return success


async def get_longterm_watchlist_full() -> list[dict]:
    """Return all active longterm stocks with all columns including automation fields."""
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT lw.ticker, lw.entry_zone_vnd, lw.conviction, lw.conviction_score,
               lw.entry_zone_method, lw.conviction_method, lw.review_flags,
               lw.pe_ratio, lw.roe, lw.dividend_yield, lw.tier,
               lw.last_reviewed_at, s.name AS sector
        FROM longterm_watchlist lw
        JOIN sectors s ON s.id = lw.sector_id
        WHERE lw.is_active = TRUE
        ORDER BY lw.tier, lw.ticker
        """
    )
    return [
        {
            "ticker": r["ticker"],
            "entry_zone_vnd": r["entry_zone_vnd"],
            "conviction": r["conviction"],
            "conviction_score": r["conviction_score"],
            "entry_zone_method": r["entry_zone_method"],
            "conviction_method": r["conviction_method"],
            "review_flags": list(r["review_flags"] or []),
            "pe_ratio": float(r["pe_ratio"]) if r["pe_ratio"] is not None else None,
            "roe": float(r["roe"]) if r["roe"] is not None else None,
            "dividend_yield": float(r["dividend_yield"])
            if r["dividend_yield"] is not None
            else None,
            "tier": r["tier"],
            "last_reviewed_at": str(r["last_reviewed_at"]) if r["last_reviewed_at"] else None,
            "sector": r["sector"],
        }
        for r in rows
    ]


# ── Sync wrappers ─────────────────────────────────────────────────────────────

get_company_research_sync = make_sync(get_company_research)
upsert_company_research_sync = make_sync(upsert_company_research)
get_longterm_watchlist_full_sync = make_sync(get_longterm_watchlist_full)


async def upsert_moat_assessment(ticker: str, moat_dict: dict) -> None:
    """Upsert moat assessment JSONB into company_research."""
    db = await get_db()
    await db.execute(
        """
        INSERT INTO company_research (ticker, sections, research_date, auto_generated)
        VALUES ($1, '{}', CURRENT_DATE, TRUE)
        ON CONFLICT (ticker) DO NOTHING
        """,
        ticker.upper(),
    )
    await db.execute(
        """
        UPDATE company_research
        SET moat_assessment = $2::jsonb, updated_at = NOW()
        WHERE ticker = $1
        """,
        ticker.upper(),
        json.dumps(moat_dict),
    )
