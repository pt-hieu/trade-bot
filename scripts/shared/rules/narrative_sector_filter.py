"""Narrative sector contamination filter (SWI-200).

Pure deterministic rule layer between the article→narrative aggregator and
``narratives.affected_tickers``. The HPG-Agri profit-cut narrative previously
absorbed TCB/MSN because the article-level ticker list (via macro fallback)
included cross-sector residue. This filter drops tickers whose sector does
not match the narrative's implied sector set.

Scope:
  * narrative_type ∈ {earnings, sector, company} → enforce sector match
  * narrative_type ∈ {macro, geopolitical, regulatory, corporate, general}
    → skip filter (narratives by design span sectors)

Fail-closed: a ticker with ``sector_map.get(ticker) is None`` is dropped under
the strict modes — better to under-attribute than poison cross-sector signal.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

logger = logging.getLogger(__name__)

# Strict modes — every ticker must map to a sector that intersects the
# narrative's affected_sectors. Other narrative_types skip the filter.
_STRICT_MODES: frozenset[str] = frozenset({"earnings", "sector", "company"})


def filter_tickers_by_sector(
    tickers: list[str],
    narrative_type: str,
    affected_sectors: list[str],
    sector_map: Mapping[str, str | None],
) -> list[str]:
    """Drop tickers whose sector ∉ implied set under strict modes.

    Args:
        tickers: Candidate ticker list (already VN-filtered upstream).
        narrative_type: Narrative type label (e.g. ``"earnings"``).
        affected_sectors: Narrative's declared affected sectors. Empty list is
            treated as "any" — caller hadn't classified yet, no drop.
        sector_map: ``ticker → sector_id`` lookup (typically built once per
            ``track_narratives`` run from ``company_profiles``).

    Returns:
        Subset of ``tickers`` that survive the sector check.
    """
    if not tickers:
        return []
    if narrative_type not in _STRICT_MODES:
        return tickers
    if not affected_sectors:
        # No declared sector to match against — keep tickers; the labeler
        # already chose an empty set, so over-filtering here would silently
        # break new earnings narratives at creation time.
        return tickers

    allowed_sectors = {s.lower() for s in affected_sectors if s}
    accepted: list[str] = []
    dropped: list[tuple[str, str | None]] = []
    for ticker in tickers:
        sector = sector_map.get(ticker)
        if sector is None:
            dropped.append((ticker, None))
            continue
        if sector.lower() in allowed_sectors:
            accepted.append(ticker)
        else:
            dropped.append((ticker, sector))
    if dropped:
        logger.info(
            "filter_tickers_by_sector(%s, sectors=%s) dropped: %s",
            narrative_type,
            sorted(allowed_sectors),
            dropped[:10],
        )
    return accepted
