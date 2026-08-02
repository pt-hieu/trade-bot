#!/usr/bin/env python3
"""
Web research tools using Lightsail API endpoints.

Replaces Firecrawl-based tools with structured data from vnstock_data + yfinance.
"""

import logging

logger = logging.getLogger(__name__)


async def fetch_macro_data() -> dict:
    """Fetch DXY, VIX, USD/VND, copper, oil, US 10Y yield, Shanghai from Lightsail API.

    Returns:
        Dict with all macro indicators, exchange_rate, and prose summary.
    """
    from shared.vnstock_client import fetch_exchange_rate, fetch_macro_global

    macro = await fetch_macro_global()
    exr = await fetch_exchange_rate()

    return {
        "dxy": macro.get("dxy", {}),
        "vix": macro.get("vix", {}),
        "usd_vnd": macro.get("usd_vnd", {}),
        "copper": macro.get("copper", {}),
        "oil": macro.get("oil", {}),
        "us_10y": macro.get("us_10y", {}),
        "shanghai": macro.get("shanghai", {}),
        "exchange_rate": exr.get("latest", {}),
        "prose": _format_macro_prose(macro, exr),
        # Pass through raw macro for insert_macro_metrics consumption
        "_raw": macro,
    }


async def fetch_foreign_flow_data(symbols: list[str] | None = None) -> dict:
    """Fetch foreign investor flow from Lightsail API.

    If no symbols provided, auto-fetches holdings for per-stock data.

    Returns:
        Dict with top_bought, top_sold, per_stock (if symbols available)
    """
    from shared.vnstock_client import fetch_foreign_top

    top = await fetch_foreign_top()

    result = {
        "top_bought": top.get("top_bought", []),
        "top_sold": top.get("top_sold", []),
    }

    # Auto-fetch holdings if no symbols specified
    if not symbols:
        try:
            from shared.neon.portfolio import tickers_held

            from .portfolio import get_holdings_async

            holdings_wrapper = await get_holdings_async()
            if "error" not in holdings_wrapper:
                slices: list[dict] = holdings_wrapper.get("holdings") or []
                symbols = tickers_held(slices)
        except Exception as e:
            logger.warning("get_holdings_async failed in foreign flow: %s", e)

    if symbols:
        from shared.vnstock_client import fetch_foreign_flow

        try:
            per_stock = await fetch_foreign_flow(symbols)
            result["per_stock"] = per_stock
        except Exception as e:
            result["per_stock_error"] = str(e)

    result["prose"] = _format_flow_prose(result)
    return result


def _format_macro_prose(macro: dict, exr: dict) -> str:
    """Format macro data as natural language."""
    parts = ["Global Macro:"]

    def _fmt(key: str, label: str, decimals: int = 2):
        d = macro.get(key, {})
        if "value" in d:
            parts.append(f"{label}: {d['value']:.{decimals}f} ({d.get('change_pct', 0):+.2f}%)")
        elif "error" in d:
            parts.append(f"{label}: N/A")

    _fmt("dxy", "DXY")
    _fmt("vix", "VIX")
    _fmt("usd_vnd", "USD/VND", decimals=0)
    _fmt("copper", "Copper", decimals=3)
    _fmt("oil", "Oil", decimals=2)
    _fmt("us_10y", "US 10Y", decimals=3)
    _fmt("shanghai", "Shanghai", decimals=2)

    latest = exr.get("latest", {})
    if latest and latest.get("usd_vnd"):
        parts.append(f"SBV rate: {latest['usd_vnd']:,.0f}")

    return " | ".join(parts)


def _format_flow_prose(data: dict) -> str:
    """Format foreign flow data as natural language."""
    parts = ["Foreign Investor Flow:"]

    bought = data.get("top_bought", [])
    sold = data.get("top_sold", [])

    if bought:
        top3 = bought[:3]
        names = [str(s.get("ticker") or s.get("symbol", "?")) for s in top3]
        parts.append(f"Top bought: {', '.join(names)}")

    if sold:
        top3 = sold[:3]
        names = [str(s.get("ticker") or s.get("symbol", "?")) for s in top3]
        parts.append(f"Top sold: {', '.join(names)}")

    # Per-stock details
    per_stock = data.get("per_stock", {})
    if per_stock:
        stock_parts = []
        for ticker, info in per_stock.items():
            if not isinstance(info, dict) or "error" in info:
                continue
            net = float(info.get("fr_net_value", 0) or 0) / 1e9
            own = info.get("fr_ownership")
            s = f"{ticker}: Net {net:+.1f}B"
            if own is not None:
                s += f" (Own: {own:.1f}%)"
            stock_parts.append(s)
        if stock_parts:
            parts.append(f"Holdings: {', '.join(stock_parts)}")

    return " | ".join(parts)


# ============================================================================
# Agent Tool Functions - Return string for LLM agents
# ============================================================================


async def tool_get_macro_global() -> str:
    """Fetch global macro indicators (DXY, VIX, USD/VND).

    For use by LLM agents. Returns natural prose string.
    """
    result = await fetch_macro_data()
    return result.get("prose", str(result))


async def tool_get_foreign_flow(symbols: str = "") -> str:
    """Fetch foreign investor flow data.

    Args:
        symbols: Comma-separated symbols for per-stock data (optional)

    For use by LLM agents. Returns natural prose string.
    """
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    result = await fetch_foreign_flow_data(symbol_list)
    return result.get("prose", str(result))
