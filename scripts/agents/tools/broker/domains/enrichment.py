"""Enrichment domain tools — flow, insider, relative strength, block trades, flow streak."""

import logging

from ...types import RequiredTickers
from ..helpers import batch_cache_key, cached_tool_call
from ..registry import ToolDomain, register_domain_tool

logger = logging.getLogger(__name__)


async def get_block_trades() -> str:
    """Get today's top block/deal trades by volume.

    Returns:
        Prose list starting with "Top Block Trades Today:" followed by
        one line per deal (ticker, shares, value). "No block trade data
        available today." when empty.
    """
    from ...enrichment import tool_get_block_trades as _impl

    return await _impl()


async def get_flow(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Get foreign/proprietary/retail flow summary for one or more tickers.

    Returns:
        Prose block per ticker with foreign net, prop net, retail net
        (in VND billions), and directional label (BUYING/SELLING).
        "No flow data" line for tickers with missing records.
    """
    from ...enrichment import tool_get_flow as _impl

    scan_date = _ctx.get("scan_date")
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("enrichment.get_flow", tickers, scan_date),
        lambda: _impl(tickers, scan_date),
    )


async def get_insider(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Get insider transaction activity (90d) for one or more tickers.

    Returns:
        Prose block per ticker listing recent insider BUY/SELL actions
        within the last 90 days (trader name, role, shares, date).
        "No insider activity" line for tickers with no transactions.
    """
    from ...enrichment import tool_get_insider as _impl

    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("enrichment.get_insider", tickers, "90d"),
        lambda: _impl(tickers),
    )


async def get_relative_strength(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Get 20d relative strength vs VN-Index for one or more tickers.

    Returns:
        One line per ticker formatted as "{TICKER} RS vs VN-Index (20d):
        {rs_value:.2f} — {label}" where label is STRONG/mild outperformer,
        in line, or WEAK/mild underperformer. "No relative strength data
        available" for tickers without records.
    """
    from ...enrichment import tool_get_relative_strength as _impl

    scan_date = _ctx.get("scan_date")
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("enrichment.get_relative_strength", tickers, scan_date),
        lambda: _impl(tickers, scan_date),
    )


def _format_flow_streak_prose(ticker: str, history: list[dict]) -> str:
    from ...flow_streak import classify_flow_streak

    upper = ticker.upper()
    if not history:
        return f"{upper}: No flow streak data available."
    try:
        result = classify_flow_streak(history)
    except Exception as error:
        logger.warning("classify_flow_streak failed for %s: %s", upper, error)
        return f"{upper}: Flow streak data unavailable: {error}"

    lines = [
        f"Flow streak for {upper}: {result['trend']} "
        f"({result['streak_days']}d {result['direction']})"
    ]
    lines.append(f"Total net: {result['total_net']:.1f}B VND over {len(history)} days")
    for entry in result["history"]:
        lines.append(f"  {entry['date']}: {entry['net']:+.1f}B")
    return "\n".join(lines)


async def _fetch_flow_streak_prose(tickers: list[str]) -> str:
    from shared.neon.flow import get_ticker_flow_streak_batch

    try:
        batch = await get_ticker_flow_streak_batch(tickers, days=5)
    except Exception as error:
        logger.warning("get_ticker_flow_streak_batch failed: %s", error)
        return "\n\n".join(
            f"{ticker.upper()}: Flow streak data unavailable: {error}" for ticker in tickers
        )

    return "\n\n".join(
        _format_flow_streak_prose(ticker, batch.get(ticker.upper(), [])) for ticker in tickers
    )


async def get_flow_streak(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Get foreign flow streak (consecutive buy/sell days) for one or more tickers.

    STRONG_BUY/SELL = 5+ consecutive days. BUILDING = 3-4 days.

    Returns:
        Prose block per ticker with header
        "Flow streak for {TICKER}: {TREND} ({N}d {DIRECTION})" followed
        by total net VND and per-day history lines. "No flow streak data
        available" for tickers with no records.
    """
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("enrichment.get_flow_streak", tickers, "5d"),
        lambda: _fetch_flow_streak_prose(tickers),
    )


register_domain_tool(
    "enrichment.get_block_trades",
    ToolDomain.ENRICHMENT,
    get_block_trades,
    returns_hint="prose — top block trades today",
)
register_domain_tool(
    "enrichment.get_flow",
    ToolDomain.ENRICHMENT,
    get_flow,
    context_keys=("scan_date", "_tool_cache"),
    accepts_tickers=True,
    returns_hint="prose per ticker — foreign/prop/retail net",
)
register_domain_tool(
    "enrichment.get_insider",
    ToolDomain.ENRICHMENT,
    get_insider,
    context_keys=("_tool_cache",),
    accepts_tickers=True,
    returns_hint="prose per ticker — insider BUY/SELL (90d)",
)
register_domain_tool(
    "enrichment.get_relative_strength",
    ToolDomain.ENRICHMENT,
    get_relative_strength,
    context_keys=("scan_date", "_tool_cache"),
    accepts_tickers=True,
    returns_hint="prose — one line per ticker (RS + label)",
)
register_domain_tool(
    "enrichment.get_flow_streak",
    ToolDomain.ENRICHMENT,
    get_flow_streak,
    context_keys=("_tool_cache",),
    accepts_tickers=True,
    returns_hint="prose per ticker — streak trend + history",
)
