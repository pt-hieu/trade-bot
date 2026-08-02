"""
Shared utilities for trading scripts.

This module exports commonly used functions and constants.
"""

# Load environment file (respects SWINGY_ENV for local vs production)
from .env import load_env

load_env()

# vnstock_data (premium) is authenticated via installer - no API key needed

from .config import (
    LLM_BASE_URL,
    LLM_MODEL,
    MAX_ARTICLE_TOKENS,
)
from .llm import call_llm
from .neon import (
    add_swing_stock_sync as add_swing_stock,
)
from .neon import (
    get_active_goal_sync as get_active_goal,
)
from .neon import (
    get_cash_balance_sync as get_cash_balance,
)
from .neon import (
    get_longterm_watchlist_sync as get_longterm_watchlist,
)
from .neon import (
    get_portfolio_holdings_sync as get_portfolio_holdings,
)

# Database functions
from .neon import (
    get_swing_watchlist_sync as get_swing_watchlist,
)
from .neon import (
    remove_swing_stock_sync as remove_swing_stock,
)
from .neon import (
    update_goal_realized_sync as update_goal_realized,
)
from .neon import (
    update_portfolio_prices_sync as update_portfolio_prices,
)
from .neon import (
    update_swing_rsi_batch_sync as update_swing_rsi_batch,
)
from .observability import (
    configure_observability,
    log_error,
    log_info,
    span,
)
from .session import (
    get_session_id,
    init_session,
)
from .telegram import (
    send_telegram,
    send_telegram_error,
)
from .trading_config import (
    TradingConfig,
    clear_trading_config_cache,
    get_trading_config,
    init_trading_config,
)

__all__ = [
    # Config
    "LLM_BASE_URL",
    "LLM_MODEL",
    "MAX_ARTICLE_TOKENS",
    # Trading config (DB-backed)
    "TradingConfig",
    "init_trading_config",
    "get_trading_config",
    "clear_trading_config_cache",
    # LLM
    "call_llm",
    # Database (Neon)
    "get_swing_watchlist",
    "get_longterm_watchlist",
    "get_portfolio_holdings",
    "get_cash_balance",
    "get_active_goal",
    "update_goal_realized",
    "update_swing_rsi_batch",
    "update_portfolio_prices",
    "add_swing_stock",
    "remove_swing_stock",
    # Telegram
    "send_telegram",
    "send_telegram_error",
    # Observability
    "configure_observability",
    "span",
    "log_info",
    "log_error",
    # Session tracking
    "init_session",
    "get_session_id",
]
