"""CRUD for company_profiles knowledge base.

User-owned data (manually populated). DB tier per data-layer rules.
Import from shared.neon (not this submodule directly).
"""

import json
import logging

from ..database import get_db
from ._sync import make_sync

logger = logging.getLogger(__name__)


_PROFILE_COLUMNS = """ticker, sector_id, business_summary,
                  revenue_segments, supply_chain, export_split,
                  macro_sensitivities, regulatory_exposure, competitive_position,
                  aliases,
                  source, version, research_date, updated_at"""


async def get_company_profile(ticker: str) -> dict | None:
    """Get full company profile for a ticker."""
    db = await get_db()
    row = await db.fetch_one(
        f"SELECT {_PROFILE_COLUMNS} FROM company_profiles WHERE ticker = $1",
        ticker.upper(),
    )
    if not row:
        return None
    return _row_to_dict(row)


async def get_profiles_batch(tickers: list[str]) -> list[dict]:
    """Get profiles for multiple tickers in one query."""
    if not tickers:
        return []
    db = await get_db()
    rows = await db.fetch_all(
        f"SELECT {_PROFILE_COLUMNS} FROM company_profiles WHERE ticker = ANY($1)",
        [t.upper() for t in tickers],
    )
    return [_row_to_dict(r) for r in rows]


async def get_universe_with_aliases(limit: int = 300) -> list[dict]:
    """News v2 Stage 1 universe injection.

    Returns active VN-listed tickers paired with sector_name and aliases for
    LLM entity spotting. Ranking: tickers in `company_profiles` first (have
    curated business knowledge / aliases), then remaining `stocks` rows by
    ticker. Truncated to `limit` to fit the 4K-token Stage 1 universe block.

    Each row: {ticker, sector_name, aliases, business_summary_short}.
    `business_summary_short` is the first sentence of business_summary
    (often empty) — Stage 1 uses ticker+aliases primarily, the sector +
    summary disambiguate near-collisions ("masan" → MSN vs MCH vs MSR).
    """
    db = await get_db()
    rows = await db.fetch_all(
        """SELECT s.ticker,
                  COALESCE(sec.name, '') AS sector_name,
                  COALESCE(cp.aliases, ARRAY[]::TEXT[]) AS aliases,
                  COALESCE(cp.business_summary, '') AS business_summary
             FROM stocks s
        LEFT JOIN company_profiles cp ON cp.ticker = s.ticker
        LEFT JOIN sectors sec ON sec.id = COALESCE(cp.sector_id, s.sector_id)
            WHERE COALESCE(s.is_active, TRUE) = TRUE
            ORDER BY (cp.aliases IS NULL) ASC,
                     array_length(cp.aliases, 1) DESC NULLS LAST,
                     s.ticker
            LIMIT $1""",
        limit,
    )
    out: list[dict] = []
    for r in rows:
        summary = (r.get("business_summary") or "").strip()
        # First-sentence trim — keep ≤120 chars per row to stay inside the
        # Stage 1 4K-token budget.
        if "." in summary:
            summary = summary.split(".", 1)[0]
        summary = summary[:120]
        out.append(
            {
                "ticker": r["ticker"],
                "sector_name": r.get("sector_name") or "",
                "aliases": list(r.get("aliases") or []),
                "business_summary_short": summary,
            }
        )
    return out


async def upsert_company_profile(ticker: str, profile: dict, source: str = "manual") -> None:
    """Upsert full company profile. Increments version on update.

    `aliases` is preserved by the ON CONFLICT clause unless `profile` carries
    a non-empty `aliases` list (caller-driven curation overwrites the
    backfilled value). Empty list / missing key keeps existing aliases —
    important so the alias_backfill_v2 rows aren't blown away by routine
    research updates.
    """
    db = await get_db()
    aliases_payload = profile.get("aliases")
    aliases_arg = list(aliases_payload) if aliases_payload else None
    await db.execute(
        """INSERT INTO company_profiles (
               ticker, sector_id, business_summary,
               revenue_segments, supply_chain, export_split,
               macro_sensitivities, regulatory_exposure, competitive_position,
               aliases,
               source, version, research_date
           ) VALUES (
               $1,
               (SELECT sector_id FROM stocks WHERE ticker = $1),
               $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb,
               COALESCE($10::TEXT[], ARRAY[]::TEXT[]),
               $9, 1, CURRENT_DATE
           )
           ON CONFLICT (ticker) DO UPDATE SET
               business_summary = EXCLUDED.business_summary,
               revenue_segments = EXCLUDED.revenue_segments,
               supply_chain = EXCLUDED.supply_chain,
               export_split = EXCLUDED.export_split,
               macro_sensitivities = EXCLUDED.macro_sensitivities,
               regulatory_exposure = EXCLUDED.regulatory_exposure,
               competitive_position = EXCLUDED.competitive_position,
               aliases = COALESCE($10::TEXT[], company_profiles.aliases),
               source = EXCLUDED.source,
               version = company_profiles.version + 1,
               research_date = CURRENT_DATE,
               updated_at = NOW()""",
        ticker.upper(),
        profile.get("business_summary"),
        json.dumps(profile.get("revenue_segments") or []),
        json.dumps(profile.get("supply_chain") or []),
        json.dumps(profile.get("export_split") or {}),
        json.dumps(profile.get("macro_sensitivities") or []),
        json.dumps(profile.get("regulatory_exposure") or []),
        json.dumps(profile.get("competitive_position") or {}),
        source,
        aliases_arg,
    )


async def get_macro_sensitivities(ticker: str) -> list[dict]:
    """Get only macro_sensitivities for a ticker (lightweight, no full profile)."""
    db = await get_db()
    row = await db.fetch_one(
        "SELECT macro_sensitivities FROM company_profiles WHERE ticker = $1",
        ticker.upper(),
    )
    if not row:
        return []
    result = _parse_jsonb(row.get("macro_sensitivities"), [])
    return result if isinstance(result, list) else []


async def resolve_tickers_by_macro_factor(factor: str) -> list[dict]:
    """Find tickers whose macro_sensitivities contain a given factor.

    Uses GIN-indexed JSONB @> containment query.
    Returns [{ticker, factor, direction, magnitude, explanation}].
    """
    return await resolve_tickers_by_factors_batch([factor])


async def resolve_tickers_by_factors_batch(factors: list[str]) -> list[dict]:
    """Find tickers affected by ANY of the given macro factors in one query.

    Returns [{ticker, factor, direction, magnitude, explanation}].
    """
    if not factors:
        return []
    db = await get_db()
    # Build JSONB containment array for OR matching
    conditions = [json.dumps([{"factor": f}]) for f in factors]
    placeholders = " OR ".join(
        f"macro_sensitivities @> ${i + 1}::jsonb" for i in range(len(conditions))
    )
    rows = await db.fetch_all(
        f"SELECT ticker, macro_sensitivities FROM company_profiles WHERE {placeholders}",
        *conditions,
    )
    results = []
    factor_set = set(factors)
    for r in rows:
        sensitivities = _parse_jsonb(r.get("macro_sensitivities"), [])
        for s in sensitivities:
            f = s.get("factor")
            # Filter to HIGH/MEDIUM magnitude — LOW-magnitude sensitivities
            # produce noise in macro fallback tagging (too many loosely-related tickers)
            if f in factor_set and (s.get("magnitude") or "UNKNOWN").upper() in ("HIGH", "MEDIUM"):
                results.append(
                    {
                        "ticker": r["ticker"],
                        "factor": f,
                        "direction": s.get("direction") or "UNKNOWN",
                        "magnitude": s.get("magnitude") or "UNKNOWN",
                        "explanation": s.get("explanation") or "",
                    }
                )
    return results


def _parse_jsonb(val, default):
    """Parse JSONB field — asyncpg may return dict/list or str."""
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default


def _row_to_dict(row) -> dict:
    """Convert DB row to dict with None-safe JSONB parsing."""
    return {
        "ticker": row["ticker"],
        "sector_id": row.get("sector_id"),
        "business_summary": row.get("business_summary") or "",
        "revenue_segments": _parse_jsonb(row.get("revenue_segments"), []),
        "supply_chain": _parse_jsonb(row.get("supply_chain"), []),
        "export_split": _parse_jsonb(row.get("export_split"), {}),
        "macro_sensitivities": _parse_jsonb(row.get("macro_sensitivities"), []),
        "regulatory_exposure": _parse_jsonb(row.get("regulatory_exposure"), []),
        "competitive_position": _parse_jsonb(row.get("competitive_position"), {}),
        "aliases": list(row.get("aliases") or []),
        "source": row.get("source") or "manual",
        "version": row.get("version") or 1,
        "research_date": str(row.get("research_date") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


# Sync wrappers — standalone CLI scripts ONLY (never before async pipelines)
get_company_profile_sync = make_sync(get_company_profile)
upsert_company_profile_sync = make_sync(upsert_company_profile)
resolve_tickers_by_macro_factor_sync = make_sync(resolve_tickers_by_macro_factor)
