"""Relative strength — delegates to shared.api.prices (API-first).

Note: get_daily_flow, get_recent_insider_transactions, and get_upcoming_corporate_events
previously lived here but now read directly from the vnstock API via shared.api.enrichment.

get_relative_strength previously read from mv_relative_strength materialized view.
Now delegates to compute_relative_strength() which computes from price history.
"""

from datetime import date


async def get_relative_strength(tickers: list[str], scan_date: date) -> dict[str, float | None]:
    """Get 20d relative strength vs VNINDEX for a batch of tickers.

    Single call to compute_relative_strength — one API round-trip fetches
    VNINDEX + all tickers together (previously fetched VNINDEX redundantly
    per ticker via fan-out).

    Args:
        tickers: list of stock codes (case-insensitive, normalized to upper).
        scan_date: kept for signature compatibility — always returns current RS.

    Returns:
        Dict mapping each uppercased ticker to its RS value (>1 = outperforming)
        or None if insufficient data. Missing tickers return None.
    """
    from shared.api.prices import compute_relative_strength

    normalized = [ticker.upper() for ticker in tickers]
    result = await compute_relative_strength(normalized, window=20)
    return {ticker: result.get(ticker) for ticker in normalized}
