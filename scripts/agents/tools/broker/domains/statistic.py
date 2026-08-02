"""Statistic domain tools."""

from typing import Literal

from ..registry import ToolDomain, register_domain_tool

StatsQueryType = Literal[
    "oversold_bounce",
    "pattern_outcome",
    "price_action",
    "consecutive_streak",
]


async def get_stats(
    query_type: StatsQueryType,
    ticker: str | None = None,
    pattern: str | None = None,
    condition: str | None = None,
    rsi_min: float = 0,
    rsi_max: float = 100,
    days_back: int = 90,
) -> str:
    """Get statistical probability data from historical patterns.

    Returns:
        str(dict) — shape depends on query_type; every variant includes a
        `prose` key. oversold_bounce→{bounce_rate, avg_next_day_change};
        pattern_outcome→{win_rate, avg_move, best_rsi_zone}; price_action→
        {reversal_rate, by_rsi_zone}; consecutive_streak→{max_consecutive,
        current_streak}. Error paths return {'error': ...}.
    """
    from ...statistics import (
        get_oversold_stats_async,
        get_pattern_stats_async,
        get_price_action_stats_async,
        get_streak_stats_async,
    )

    if query_type == "oversold_bounce":
        result = await get_oversold_stats_async(ticker, 30.0, days_back)
    elif query_type == "pattern_outcome":
        if not pattern:
            return '{"error": "pattern required for pattern_outcome"}'
        result = await get_pattern_stats_async(pattern, rsi_min, rsi_max, days_back)
    elif query_type == "price_action":
        result = await get_price_action_stats_async(days_back)
    elif query_type == "consecutive_streak":
        if not ticker or not condition:
            return '{"error": "ticker and condition required"}'
        result = await get_streak_stats_async(ticker, condition, days_back)
    else:
        return f'{{"error": "Unknown query_type: {query_type}"}}'
    return str(result)


async def get_strategy_performance() -> str:
    """Get strategy win rates by regime and rolling performance.

    Returns:
        Prose starting with "Strategy Performance:" followed by two
        sections: "By Strategy x Regime" (top 8 strategy/regime pairs
        with win rate, trades, avg P&L) and "Rolling Performance" (7d,
        30d, 90d win rates + trade counts).
    """
    from ...statistics import tool_get_strategy_performance as _impl

    return await _impl()


register_domain_tool(
    "statistic.get_stats",
    ToolDomain.STATISTIC,
    get_stats,
    returns_hint="str(dict) — query-specific stats + prose key",
)
register_domain_tool(
    "statistic.get_strategy_performance",
    ToolDomain.STATISTIC,
    get_strategy_performance,
    returns_hint="prose — strategy×regime + 7/30/90d rolling",
)
