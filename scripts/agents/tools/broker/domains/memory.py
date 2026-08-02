"""Memory domain tools — similar days, trading rules, winning/losing patterns."""

from typing import Literal

from ..registry import ToolDomain, register_domain_tool

MarketRegime = Literal["RISK_ON", "NEUTRAL", "RISK_OFF"]
MacroRegime = Literal["CALM", "CAUTIOUS", "ELEVATED", "CRISIS"]


async def get_similar_days(
    regime: MarketRegime,
    hot_sectors: str = "",
    cold_sectors: str = "",
    macro: MacroRegime | None = None,
    vix: float | None = None,
) -> str:
    """Find past days with similar market context and their outcomes.

    Returns:
        Prose listing up to 3 historically similar days with their
        outcomes (entries/exits, win rate) plus an interpretation blurb.
        "No similar historical days found with embeddings." when none
        match. "Memory search unavailable: {error}" on failure.
    """
    from ...memory import tool_get_similar_days as _impl

    result = await _impl(regime, hot_sectors, cold_sectors, macro, vix)
    return str(result)


async def get_trading_rules(
    regime: MarketRegime,
    sectors: str = "",
    rsi: float | None = None,
    macro: MacroRegime | None = None,
) -> str:
    """Get validated trading rules for current conditions.

    Returns:
        Prose with 3 grouped sections (Entry rules, Exit rules, Avoid
        rules) each listing up to 5 validated rules with confidence
        scores. "No trading rules found for current conditions." when
        empty. "Trading rules lookup failed: {error}" on failure.
    """
    from ...memory import tool_get_trading_rules as _impl

    result = await _impl(regime, sectors, rsi, macro)
    return str(result)


async def get_winning_patterns(regime: MarketRegime, hot_sectors: str = "") -> str:
    """Find winning patterns similar to current conditions.

    Returns:
        Prose listing up to 3 winning patterns from similar historical
        contexts with their win rate, avg P&L, and pattern description.
        "No similar winning patterns found." when empty.
        "Pattern search unavailable: {error}" on failure.
    """
    from ...memory import tool_get_winning_patterns as _impl

    result = await _impl(regime, hot_sectors)
    return str(result)


async def get_losing_patterns(regime: MarketRegime, cold_sectors: str = "") -> str:
    """Find losing patterns to avoid in current conditions.

    Returns:
        Prose listing up to 3 losing patterns with their loss rate,
        avg drawdown, and pattern description. "No similar losing
        patterns found." when empty. "Pattern search unavailable:
        {error}" on failure.
    """
    from ...memory import tool_get_losing_patterns as _impl

    result = await _impl(regime, cold_sectors)
    return str(result)


register_domain_tool(
    "memory.get_similar_days",
    ToolDomain.MEMORY,
    get_similar_days,
    returns_hint="prose — up to 3 similar days + outcomes",
)
register_domain_tool(
    "memory.get_trading_rules",
    ToolDomain.MEMORY,
    get_trading_rules,
    returns_hint="prose — entry/exit/avoid rules (up to 5 each)",
)
register_domain_tool(
    "memory.get_winning_patterns",
    ToolDomain.MEMORY,
    get_winning_patterns,
    returns_hint="prose — up to 3 winning patterns",
)
register_domain_tool(
    "memory.get_losing_patterns",
    ToolDomain.MEMORY,
    get_losing_patterns,
    returns_hint="prose — up to 3 losing patterns",
)
