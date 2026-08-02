"""Phase-0 fetchers for held-position thesis + valuation prose.

Splits the `position_thesis_prose` / `position_valuation_prose` fetchers out
of `enrichment_loader.py` so the inject-instead-of-tool batch for held
positions has a single home. Both delegate to the public per-ticker helpers
in `agents.tools.broker.domains` so the broker tool and Phase-0 path share
one fetch+gather body.
"""

from __future__ import annotations


def extract_held_tickers(holdings: list[dict] | None) -> list[str]:
    """Pull the unique held-ticker list from `holdings` slices.

    Dual-listed tickers (one slice per plan_type) collapse to a single fetch
    so we don't pay duplicate Neon round-trips for thesis / valuation prose.
    """
    if not holdings:
        return []
    seen: list[str] = []
    for slice_row in holdings:
        ticker = slice_row.get("ticker") if isinstance(slice_row, dict) else None
        if not ticker:
            continue
        upper = ticker.upper()
        if upper not in seen:
            seen.append(upper)
    return seen


async def fetch_position_thesis_prose(held_tickers: list[str]) -> dict[str, str]:
    """Per-ticker thesis pillars + kill criteria + last update prose."""
    from agents.tools.broker.domains.portfolio import fetch_thesis_prose_by_ticker

    return await fetch_thesis_prose_by_ticker(held_tickers)


async def fetch_position_valuation_prose(held_tickers: list[str]) -> dict[str, str]:
    """Per-ticker `=== VALUATION === / EARNINGS QUALITY === / VALUATION HISTORY ===` prose."""
    from agents.tools.broker.domains.fundamental import gather_full_analysis_by_ticker

    return await gather_full_analysis_by_ticker(held_tickers)
