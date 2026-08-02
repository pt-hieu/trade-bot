"""
Agent tools for searching articles and fetching market data.
"""

from .articles import (
    list_articles_async,
    read_article_async,
    search_articles_async,
)
from .market import (
    get_macro_history_async,
    get_macro_metrics_async,
    get_market_regime,
    get_market_regime_async,
    get_regime_history,
    get_regime_history_async,
    get_sector_rotation,
    get_sector_rotation_async,
    get_sector_technicals,
    get_vnindex_technicals,
)
from .memory import (
    get_similar_historical_days,
    get_similar_patterns_for_context,
    get_trading_rules_for_context,
    tool_get_losing_patterns,
    tool_get_similar_days,
    tool_get_trading_rules,
    tool_get_winning_patterns,
)
from .portfolio import (
    get_cash_balance_async,
    get_goal_progress_async,
    get_holdings_async,
    get_learnings_async,
    get_longterm_watchlist_async,
    get_position_scale_factor,
    get_recent_trades_async,
)
from .technicals import get_ticker_data, get_ticker_data_async
from .web_research import (
    fetch_foreign_flow_data,
    fetch_macro_data,
    tool_get_foreign_flow,
    tool_get_macro_global,
)

__all__ = [
    # Articles (async for agents)
    "search_articles_async",
    "read_article_async",
    "list_articles_async",
    # Technicals
    "get_ticker_data",
    "get_ticker_data_async",
    # Portfolio (async)
    "get_holdings_async",
    "get_cash_balance_async",
    "get_longterm_watchlist_async",
    "get_recent_trades_async",
    "get_goal_progress_async",
    "get_learnings_async",
    "get_position_scale_factor",
    # Web Research (replaces Firecrawl)
    "fetch_macro_data",
    "fetch_foreign_flow_data",
    "tool_get_macro_global",
    "tool_get_foreign_flow",
    # Market (sync for CLI, async for agents)
    "get_vnindex_technicals",
    "get_sector_rotation",
    "get_market_regime",
    "get_regime_history",
    "get_sector_technicals",
    "get_market_regime_async",
    "get_sector_rotation_async",
    "get_macro_metrics_async",
    "get_regime_history_async",
    "get_macro_history_async",
    # Memory (similarity search)
    "get_similar_historical_days",
    "get_similar_patterns_for_context",
    "get_trading_rules_for_context",
    "tool_get_similar_days",
    "tool_get_trading_rules",
    "tool_get_winning_patterns",
    "tool_get_losing_patterns",
]
