"""Sync wrappers for CLI scripts (backwards compatibility)."""

from __future__ import annotations

import logging
from datetime import date
from typing import cast

from shared.async_compat import run_async as _run_async

from .prose import _format_technicals_prose

logger = logging.getLogger(__name__)


def get_ticker_data(ticker: str, scan_date: date | None = None) -> dict:
    """Get latest price, RSI, MACD, MA20 for any ticker.

    Returns:
        Dict with price data, technical indicators, and prose summary.
        Use result["prose"] for natural language description.
    """
    from shared.api.technicals import get_ticker_technicals

    ticker = ticker.upper()

    try:
        result = cast(dict, _run_async(get_ticker_technicals(ticker)))
        if "error" not in result:
            result["prose"] = _format_technicals_prose(result)
            return result
    except Exception as e:
        logger.warning("get_ticker_technicals(%s) failed: %s", ticker, e)

    error_result = {"ticker": ticker, "error": f"No data found for {ticker} on {scan_date}"}
    error_result["prose"] = f"{ticker}: No data available for {scan_date}."
    return error_result
