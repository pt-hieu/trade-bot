"""API-first data access layer.

Unit conventions (rule 18):
- All price values returned in VND integers (e.g., 30500)
- All percentage fields (ROE, margins) returned as whole-number % (e.g., 28.27)
- All rates (bounce_rate, win_rate) returned as decimal 0-1 (e.g., 0.65)
- All ratios (PE, PB, D/E) returned as-is (e.g., 12.5)
"""

from .commodities import get_commodity_prices
from .enrichment import (
    get_daily_flow,
    get_daily_flow_batch,
    get_recent_insider_transactions,
    get_recent_insider_transactions_batch,
    get_upcoming_corporate_events,
)
from .fundamentals import (
    get_financial_ratios,
    get_financial_ratios_batch,
    get_financial_statements,
    get_latest_financial_statement,
)
from .prices import compute_daily_return, compute_relative_strength, get_prices
from .statistics import (
    get_consecutive_pattern_days,
    get_pattern_outcome_stats,
    get_price_action_analysis,
    get_rsi_oversold_bounces,
)
from .technicals import get_technicals

__all__ = [
    "get_financial_ratios",
    "get_financial_ratios_batch",
    "get_financial_statements",
    "get_latest_financial_statement",
    "get_daily_flow",
    "get_daily_flow_batch",
    "get_recent_insider_transactions",
    "get_recent_insider_transactions_batch",
    "get_upcoming_corporate_events",
    # prices
    "get_prices",
    "compute_daily_return",
    "compute_relative_strength",
    # technicals
    "get_technicals",
    # statistics
    "get_rsi_oversold_bounces",
    "get_pattern_outcome_stats",
    "get_price_action_analysis",
    "get_consecutive_pattern_days",
    # commodities
    "get_commodity_prices",
]
