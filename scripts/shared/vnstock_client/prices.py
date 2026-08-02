"""Price history + symbols endpoints (single + batch)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from ._client import (
    VNSTOCK_API_URL,
    _check_configured,
    _get_client,
    _get_headers,
    _request_with_retry,
)

logger = logging.getLogger(__name__)


async def fetch_history(
    symbol: str,
    source: str = "VCI",
    start: str | None = None,
    end: str | None = None,
    interval: str = "1D",
) -> dict:
    """Fetch price history for a single symbol.

    Args:
        symbol: Stock symbol (e.g., 'FPT', 'TCB')
        source: Data source (default: 'VCI')
        start: Start date (YYYY-MM-DD), defaults to 100 days ago
        end: End date (YYYY-MM-DD), defaults to today
        interval: Time interval (default: '1D')

    Returns:
        Dict with 'symbol', 'data' (list of OHLCV records), 'count'
    """
    _check_configured()

    if not start:
        start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.now().strftime("%Y-%m-%d")

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/quote/history",
        params={
            "symbol": symbol,
            "source": source,
            "start": start,
            "end": end,
            "interval": interval,
        },
        headers=_get_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


async def get_price_on_date(
    ticker: str,
    target_date: date,
    source: str = "VCI",
    lookback_days: int = 10,
) -> dict | None:
    """Fetch closing price for a ticker on a specific date.

    Returns raw API format: {"close": float (thousands VND), "volume": int}
    or None if no data for that date. Callers convert to VND integers via * 1000.

    Args:
        lookback_days: fallback window for holidays/weekends. Default 10
            covers worst-case Tet (9 calendar days).
    """
    date_str = (
        target_date.strftime("%Y-%m-%d") if hasattr(target_date, "strftime") else str(target_date)
    )
    result = await fetch_history(ticker, source=source, start=date_str, end=date_str)

    records = result.get("data", [])
    if not records:
        buffer_start = (target_date - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        result = await fetch_history(ticker, source=source, start=buffer_start, end=date_str)
        records = result.get("data", [])
        if not records:
            return None

    last_record = records[-1]
    try:
        return {
            "close": float(last_record["close"]),
            "volume": int(last_record.get("volume") or 0),
        }
    except (KeyError, TypeError, ValueError) as error:
        logger.warning("Failed to parse price record for %s on %s: %s", ticker, target_date, error)
        return None


async def fetch_history_batch(
    symbols: list[str],
    source: str = "VCI",
    start: str | None = None,
    end: str | None = None,
    interval: str = "1D",
    chunk_size: int = 10,
) -> dict:
    """Fetch price history for multiple symbols, chunked to avoid server OOM."""
    _check_configured()

    if not start:
        start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.now().strftime("%Y-%m-%d")

    results = {}
    chunks = [symbols[i : i + chunk_size] for i in range(0, len(symbols), chunk_size)]

    for chunk in chunks:
        # SWI-357: route through _request_with_retry so transient 5xx (a single
        # bad upstream call) no longer collapses the entire morning scan into
        # blanket tech_data_error. Mirrors the precedent already in
        # fetch_technicals_batch (corporate.py).
        resp = await _request_with_retry(
            "get",
            f"{VNSTOCK_API_URL}/quote/history/batch",
            params={
                "symbols": ",".join(chunk),
                "source": source,
                "start": start,
                "end": end,
                "interval": interval,
            },
            timeout=180.0,
        )
        results.update(resp.json())

    return results


async def fetch_symbols(source: str = "VCI") -> dict:
    """Fetch all available symbols.

    Args:
        source: Data source (default: 'VCI')

    Returns:
        Dict with 'data' (list of symbol records), 'count'
    """
    _check_configured()

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/listing/symbols",
        params={"source": source},
        headers=_get_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()
