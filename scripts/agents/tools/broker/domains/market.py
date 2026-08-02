"""Market domain tools — rotation, sector data, midday prices."""

import logging

from ..registry import ToolDomain, register_domain_tool

logger = logging.getLogger(__name__)

PRICE_MULTIPLIER = 1000


async def get_rotation(*, _ctx: dict) -> str:
    """Get hot/cold sector rotation data.

    Returns:
        Stringified dict with {hot_sectors: list[str], cold_sectors:
        list[str], rotation_signal: str, market_regime: str}. On missing
        data: "{'error': 'No sector rotation data found for {date}'}".
        On exception: "Failed to get sector rotation: {error}".
    """
    from shared.neon import get_sector_rotation

    scan_date = _ctx.get("scan_date")
    try:
        result = await get_sector_rotation(scan_date)
        return str(result)
    except Exception as error:
        return f"Failed to get sector rotation: {error}"


async def get_sector_data(*, _ctx: dict) -> str:
    """Get RSI and price data for all stocks grouped by sector.

    Returns:
        Stringified dict keyed by sector name mapping to a list of
        per-ticker entries with RSI, price, trend, and levels. "{'error':
        ...}" dict-as-str when the technicals fetch fails.
    """
    from ...market import get_sector_technicals

    scan_date = _ctx.get("scan_date")
    result = get_sector_technicals(scan_date)
    return str(result)


async def get_midday_prices(*, _ctx: dict) -> str:
    """Get actual midday OHLCV prices fetched at market break.

    Returns:
        Prose starting with "Midday Prices (at market break):" followed
        by one line per ticker formatted as "{TICKER}: {close} ({±pct}%)
        O:{open} H:{high} L:{low}". "INSUFFICIENT DATA: ..." when the
        upstream fetch produced no data.
    """
    midday_prices = _ctx.get("midday_prices") or {}
    if not midday_prices:
        logger.warning("market.get_midday_prices: empty — upstream fetch may have failed")
        return (
            "INSUFFICIENT DATA: No midday prices available. "
            "Upstream fetch may have failed. Defer to morning plan."
        )

    lines = ["Midday Prices (at market break):"]
    for ticker in sorted(midday_prices):
        data = midday_prices[ticker]
        if "error" in data:
            continue
        open_price = data["open"]
        high_price = data["high"]
        low_price = data["low"]
        close_price = data["close"]
        change_pct = (close_price - open_price) / open_price * 100 if open_price > 0 else 0
        sign = "+" if change_pct >= 0 else ""
        lines.append(
            f"{ticker}: {close_price * PRICE_MULTIPLIER:,.0f} ({sign}{change_pct:.1f}%) "
            f"O:{open_price * PRICE_MULTIPLIER:,.0f} H:{high_price * PRICE_MULTIPLIER:,.0f} "
            f"L:{low_price * PRICE_MULTIPLIER:,.0f}"
        )
    return "\n".join(lines)


register_domain_tool(
    "market.get_rotation",
    ToolDomain.MARKET,
    get_rotation,
    context_keys=("scan_date",),
    returns_hint="str(dict) — {hot[], cold[], signal, regime} | 'Failed...'",
)
register_domain_tool(
    "market.get_sector_data",
    ToolDomain.MARKET,
    get_sector_data,
    context_keys=("scan_date",),
    returns_hint="str(dict[sector → list[ticker_technicals]])",
)
register_domain_tool(
    "market.get_midday_prices",
    ToolDomain.MARKET,
    get_midday_prices,
    context_keys=("midday_prices",),
    returns_hint="prose — per-ticker OHLCV + % change",
)
