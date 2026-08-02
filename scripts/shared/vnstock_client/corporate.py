"""Per-ticker corporate endpoints: news, financials, technicals, midday, enrichment."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ._client import (
    VNSTOCK_API_URL,
    _check_configured,
    _get_client,
    _get_headers,
    _request_with_retry,
)
from .prices import fetch_history_batch

logger = logging.getLogger(__name__)


async def fetch_news_articles(
    sites: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    """Fetch Vietnamese news articles from RSS feeds via Lightsail."""
    _check_configured()
    params: dict[str, str | int] = {"limit": limit}
    if sites:
        params["sites"] = ",".join(sites)

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/news/articles",
        headers=_get_headers(),
        params=params,
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()

    failed_sites = data.get("failed_sites", [])
    if failed_sites:
        logger.warning("RSS feeds failed for: %s", ", ".join(failed_sites))

    return data.get("articles", [])


async def fetch_financial_statements(
    symbol: str,
    statement_type: str = "income",
    period: str = "quarter",
    source: str = "VCI",
    limit: int = 8,
) -> dict:
    """Fetch financial statements for a single symbol."""
    _check_configured()

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/financials/statements",
        params={
            "symbol": symbol,
            "statement_type": statement_type,
            "period": period,
            "source": source,
            "limit": limit,
        },
        headers=_get_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_financial_ratios(
    symbol: str,
    period: str = "quarter",
    source: str = "VCI",
    limit: int = 8,
) -> dict:
    """Fetch financial ratios for a single symbol."""
    _check_configured()

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/financials/ratios",
        params={
            "symbol": symbol,
            "period": period,
            "source": source,
            "limit": limit,
        },
        headers=_get_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_financials_batch(
    symbols: list[str],
    statement_type: str = "income",
    period: str = "quarter",
    limit: int = 8,
) -> dict:
    """Fetch financial statements for multiple symbols (one-by-one)."""
    _check_configured()
    results = {}

    client = _get_client()
    for symbol in symbols:
        try:
            resp = await client.get(
                f"{VNSTOCK_API_URL}/financials/statements",
                params={
                    "symbol": symbol,
                    "statement_type": statement_type,
                    "period": period,
                    "limit": limit,
                },
                headers=_get_headers(),
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            results[symbol.upper()] = {"data": data.get("data", []), "count": data.get("count", 0)}
        except Exception as e:
            results[symbol.upper()] = {"error": str(e)}

    return results


async def fetch_technicals(
    symbol: str,
    source: str = "VCI",
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Fetch technical indicators for a single symbol via vnstock_ta."""
    _check_configured()

    if not start:
        start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.now().strftime("%Y-%m-%d")

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/technicals",
        params={
            "symbol": symbol,
            "source": source,
            "start": start,
            "end": end,
        },
        headers=_get_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_technicals_history(
    symbol: str,
    source: str = "VCI",
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Fetch historical technicals time series for a single symbol."""
    _check_configured()

    if not start:
        start = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.now().strftime("%Y-%m-%d")

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/technicals/history",
        params={
            "symbol": symbol,
            "source": source,
            "start": start,
            "end": end,
        },
        headers=_get_headers(),
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_technicals_batch(
    symbols: list[str],
    source: str = "VCI",
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Fetch technical indicators for multiple symbols via vnstock_ta."""
    _check_configured()

    if not start:
        start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    if not end:
        end = datetime.now().strftime("%Y-%m-%d")

    resp = await _request_with_retry(
        "get",
        f"{VNSTOCK_API_URL}/technicals/batch",
        params={
            "symbols": ",".join(symbols),
            "source": source,
            "start": start,
            "end": end,
        },
        timeout=120.0,
    )
    return resp.json()


async def fetch_midday_snapshot(
    symbols: list[str],
    date: str,
    source: str = "VCI",
) -> dict:
    """Fetch 15-min bars for a date, return the morning session close bar.

    Uses existing /quote/history/batch with interval="15m".
    Returns dict mapping symbol -> {open, high, low, close, volume} or {error: str}.
    """
    results = await fetch_history_batch(
        symbols=symbols,
        source=source,
        start=date,
        end=date,
        interval="15m",
    )

    midday: dict = {}
    for symbol, data in results.items():
        if "error" in data:
            midday[symbol] = data
            continue

        bars = data.get("data", [])
        if not bars:
            midday[symbol] = {"error": "No intraday bars returned"}
            continue

        morning_close = None
        for bar in bars:
            t = str(bar.get("time", ""))
            if "11:30" in t or "11:15" in t:
                morning_close = bar
                break

        if morning_close is None:
            morning_close = bars[-1]

        midday[symbol] = {
            "open": float(morning_close.get("open", 0)),
            "high": float(morning_close.get("high", 0)),
            "low": float(morning_close.get("low", 0)),
            "close": float(morning_close.get("close", 0)),
            "volume": int(morning_close.get("volume", 0)),
        }

    return midday


async def fetch_ticker_enrichment(
    symbols: list[str],
    modules: list[str] | None = None,
    days: int = 5,
) -> dict:
    """Fetch composite enrichment data per ticker (flow, prop, orders, insider, events)."""
    _check_configured()
    if modules is None:
        modules = ["flow", "prop", "orders"]

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/ticker/enrichment",
        params={
            "symbols": ",".join(symbols),
            "modules": ",".join(modules),
            "days": days,
        },
        headers=_get_headers(),
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()
