"""Sector metadata + per-sector screening thresholds.

L5 of the 2026-04-24 regime+screen fix moves fundamental-screen thresholds
from a hardcoded BANK_TICKERS frozenset + flat trading_config defaults →
per-sector overrides joined via ``stocks.sector_id``. This module is the
single read path for that join.

Any column in ``sector_screening_overrides`` left NULL means "inherit the
trading_config default for this metric", so callers merge the override
dict on top of the flat defaults. No sector membership (``stocks.sector_id
IS NULL``) falls back to pure defaults.
"""

from __future__ import annotations

from typing import TypedDict

from ..database import get_db


class SectorThresholdRow(TypedDict, total=False):
    """Per-ticker resolved screening thresholds.

    ``sector_name`` is carried for audit / downstream prompt context so
    the screen rejection row can explain *why* a softer D/E cap applies.
    A missing key means "no sector override" — the caller MUST fall back
    to the matching ``cfg.screen_*`` field.
    """

    sector_name: str
    max_pe: float
    max_pb: float
    min_roe_pct: float
    min_margin_pct: float
    max_de: float


async def get_sector_thresholds_batch(
    tickers: list[str],
) -> dict[str, SectorThresholdRow]:
    """Resolve per-ticker sector thresholds in one batched query.

    Args:
        tickers: Upper-case ticker symbols. Unknown tickers simply get
            no entry in the return dict — the caller applies defaults.

    Returns:
        ``{ticker: SectorThresholdRow}`` with only the non-NULL override
        fields populated, plus ``sector_name`` for audit. Tickers with no
        ``sector_id`` are omitted (caller treats as default-only).
    """
    if not tickers:
        return {}

    db = await get_db()
    upper_tickers = [t.upper() for t in tickers if t]
    rows = await db.fetch_all(
        """
        SELECT s.ticker,
               sec.name           AS sector_name,
               sso.max_pe         AS max_pe,
               sso.max_pb         AS max_pb,
               sso.min_roe_pct    AS min_roe_pct,
               sso.min_margin_pct AS min_margin_pct,
               sso.max_de         AS max_de
        FROM stocks s
        JOIN sectors sec ON s.sector_id = sec.id
        LEFT JOIN sector_screening_overrides sso ON sso.sector_id = sec.id
        WHERE s.ticker = ANY($1::text[])
        """,
        upper_tickers,
    )

    out: dict[str, SectorThresholdRow] = {}
    for row in rows:
        ticker = row["ticker"].upper()
        entry: SectorThresholdRow = {"sector_name": row["sector_name"]}
        for key in ("max_pe", "max_pb", "min_roe_pct", "min_margin_pct", "max_de"):
            value = row.get(key)
            if value is not None:
                entry[key] = float(value)  # type: ignore[literal-required]
        out[ticker] = entry
    return out


__all__ = ["SectorThresholdRow", "get_sector_thresholds_batch"]
