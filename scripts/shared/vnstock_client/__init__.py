"""Client for vnstock API server on AWS Lightsail.

All stock data is fetched from the API server.
Requires VNSTOCK_API_URL and VNSTOCK_API_KEY environment variables.

Module layout (post-modularisation, SWI-212, FIX 4 — 4 cohesion modules):
  * ``_client.py`` — retry/headers/lifecycle (_get_client, _request_with_retry).
  * ``prices.py`` — history + on_date + history_batch + symbols.
  * ``market_data.py`` — breadth/flow/foreign/macro globals/commodities/valuation.
  * ``corporate.py`` — news + financial_*/technicals_*/midday/enrichment.
  * ``__init__.py`` — re-exports the full public surface so consumers keep
    their existing ``from shared.vnstock_client import X`` imports.
"""

from __future__ import annotations

from ._client import (
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
    RETRYABLE_STATUS_CODES,
    VNSTOCK_API_KEY,
    VNSTOCK_API_URL,
    check_health,
    close_client,
)
from .corporate import (
    fetch_financial_ratios,
    fetch_financial_statements,
    fetch_financials_batch,
    fetch_midday_snapshot,
    fetch_news_articles,
    fetch_technicals,
    fetch_technicals_batch,
    fetch_technicals_history,
    fetch_ticker_enrichment,
)
from .market_data import (
    fetch_commodity_prices,
    fetch_exchange_rate,
    fetch_foreign_flow,
    fetch_foreign_top,
    fetch_macro_global,
    fetch_market_breadth,
    fetch_market_deals,
    fetch_market_valuation,
    fetch_vn_economic_snapshot,
)
from .prices import (
    fetch_history,
    fetch_history_batch,
    fetch_symbols,
    get_price_on_date,
)

__all__ = [
    "MAX_RETRIES",
    "RETRY_BACKOFF_BASE",
    "RETRYABLE_STATUS_CODES",
    "VNSTOCK_API_KEY",
    "VNSTOCK_API_URL",
    "check_health",
    "close_client",
    "fetch_commodity_prices",
    "fetch_exchange_rate",
    "fetch_financial_ratios",
    "fetch_financial_statements",
    "fetch_financials_batch",
    "fetch_foreign_flow",
    "fetch_foreign_top",
    "fetch_history",
    "fetch_history_batch",
    "fetch_macro_global",
    "fetch_market_breadth",
    "fetch_market_deals",
    "fetch_market_valuation",
    "fetch_midday_snapshot",
    "fetch_news_articles",
    "fetch_symbols",
    "fetch_technicals",
    "fetch_technicals_batch",
    "fetch_technicals_history",
    "fetch_ticker_enrichment",
    "fetch_vn_economic_snapshot",
    "get_price_on_date",
]
