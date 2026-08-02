"""Stateless filters over raw active-catalyst dicts.

Lives in its own module so call sites can import the predicate without
pulling in the heavier `catalyst_summaries` graph (lifecycle resolver,
geopolitical phase tables, etc.).
"""

from __future__ import annotations


def filter_high_positive_catalyst_tickers(raw_catalysts: list[dict]) -> dict[str, str]:
    """Map ticker → catalyst_id for HIGH-confidence POSITIVE catalysts.

    Shared between Phase 0 rally_readmit and the weekly watchlist guard so
    both apply the same predicate the rest of the codebase uses
    (confidence == 'HIGH' AND impact == 'POSITIVE').
    """
    out: dict[str, str] = {}
    for catalyst in raw_catalysts:
        if str(catalyst.get("confidence") or "").upper() != "HIGH":
            continue
        if str(catalyst.get("impact") or "").upper() != "POSITIVE":
            continue
        catalyst_id = str(catalyst.get("id") or "")
        for ticker in catalyst.get("affected") or []:
            out.setdefault(str(ticker).upper(), catalyst_id)
    return out
