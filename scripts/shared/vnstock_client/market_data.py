"""Market-wide endpoints: breadth, foreign flow, macro globals, commodities, valuation."""

from __future__ import annotations

import logging

from ._client import (
    VNSTOCK_API_URL,
    _check_configured,
    _get_client,
    _get_headers,
    _request_with_retry,
)

logger = logging.getLogger(__name__)


async def fetch_macro_global() -> dict:
    """Fetch DXY and VIX via Lightsail (yfinance).

    Returns:
        Dict with dxy: {value, change_pct}, vix: {value, change_pct}
    """
    _check_configured()

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/macro/global",
        headers=_get_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_market_breadth() -> dict:
    """Fetch market advance/decline breadth from VNINDEX.

    Returns:
        Dict with advance, decline, breadth_ratio
    """
    _check_configured()

    client = _get_client()
    try:
        resp = await client.get(
            f"{VNSTOCK_API_URL}/market/breadth",
            headers=_get_headers(),
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as error:
        logger.warning("Market breadth fetch failed: %s", error)
        return {}


async def fetch_exchange_rate(
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Fetch USD/VND exchange rate via Lightsail (vnstock_data).

    Returns:
        Dict with latest: {rate data}, data: [...], count
    """
    _check_configured()
    params = {}
    if start:
        params["start"] = start
    if end:
        params["end"] = end

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/macro/exchange-rate",
        headers=_get_headers(),
        params=params,
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_foreign_flow(
    symbols: list[str],
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Fetch foreign investor flow per symbol via Lightsail (vnstock_data)."""
    _check_configured()
    params = {"symbols": ",".join(symbols)}
    if start:
        params["start"] = start
    if end:
        params["end"] = end

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/trading/foreign",
        headers=_get_headers(),
        params=params,
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_foreign_top(limit: int = 10, date: str | None = None) -> dict:
    """Fetch top stocks bought/sold by foreign investors."""
    _check_configured()
    params: dict = {"limit": limit}
    if date:
        params["date"] = date

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/trading/foreign-top",
        headers=_get_headers(),
        params=params,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_market_deals(limit: int = 20) -> list[dict]:
    """Fetch top tickers by block trade / deal volume."""
    _check_configured()

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/market/deals",
        params={"limit": limit},
        headers=_get_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


async def fetch_commodity_prices(
    commodities: list[str] | None = None,
) -> dict:
    """Fetch commodity prices with 5d/20d changes from /commodities/prices."""
    _check_configured()
    params: dict[str, str] = {}
    if commodities:
        params["commodities"] = ",".join(commodities)
    response = await _request_with_retry(
        "get",
        f"{VNSTOCK_API_URL}/commodities/prices",
        params=params,
        timeout=30.0,
    )
    return response.json()


async def fetch_market_valuation() -> dict:
    """Fetch VN-Index PE/PB with 5Y percentile from /market/valuation."""
    _check_configured()
    response = await _request_with_retry(
        "get",
        f"{VNSTOCK_API_URL}/market/valuation",
        timeout=30.0,
    )
    return response.json()


async def fetch_vn_economic_snapshot() -> dict:
    """Fetch VN economy snapshot from /macro/vn-snapshot."""
    _check_configured()
    response = await _request_with_retry(
        "get",
        f"{VNSTOCK_API_URL}/macro/vn-snapshot",
        timeout=30.0,
    )
    return response.json()
