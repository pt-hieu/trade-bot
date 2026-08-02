"""
Shared watchlist utilities.
"""

from collections.abc import Sequence
from typing import Any

# Pseudo-sector key under which `merge_holdings_into_watchlist` stashes held
# tickers that are NOT in the real watchlist. Coverage logic excludes this
# key — see `WATCHLIST_PSEUDO_SECTORS` in shared/rules/belief_coverage.py.
HOLDINGS_SECTOR_KEY: str = "holdings"


def merge_holdings_into_watchlist(watchlist: dict, holdings: Sequence[Any]) -> dict:
    """Add portfolio holdings to watchlist for price/tech fetching.

    Holdings not already in watchlist are added to a 'holdings' pseudo-sector.
    This ensures all portfolio positions get daily price/technical data.

    Args:
        watchlist: sector -> [ticker] dict (e.g. from get_swing_watchlist)
        holdings: list of (ticker, plan_type) slices (get_portfolio_holdings)

    Returns:
        Merged watchlist with extra holdings under 'holdings' key.
    """
    if not watchlist:
        return {}
    merged = {**watchlist}
    if holdings:
        existing = {t for tickers in watchlist.values() for t in tickers}
        held_tickers: list[str] = []
        for slice_row in holdings:
            ticker = slice_row.get("ticker")
            if ticker and ticker not in existing and ticker not in held_tickers:
                held_tickers.append(ticker)
        if held_tickers:
            merged[HOLDINGS_SECTOR_KEY] = held_tickers
            print(f"Added {len(held_tickers)} holdings to fetch list: {', '.join(held_tickers)}")
    return merged
