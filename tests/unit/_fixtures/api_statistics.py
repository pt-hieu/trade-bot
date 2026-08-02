"""Shared OHLCV/RSI helpers for shared/api/statistics test splits."""

from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Reference "now" for test data anchored at 2026-02-XX. Anchor 30 days
# after the latest test data (2026-02-13) so days_back=90 windows cover
# the full fixture range without depending on real wall clock.
TEST_NOW = datetime(2026, 3, 15, 12, 0, 0)


def _ohlcv(date_str: str, close: float, vol_mult: float = 1.0) -> dict:
    """Build one OHLCV record with controllable close-at-low behaviour."""
    return {
        "time": date_str,
        "open": close * 1.01,  # Opens slightly above close → NOT closed_at_low
        "high": close * 1.03,
        "low": close * 0.97,
        "close": close,
        "volume": int(1_000_000 * vol_mult),
    }


def _ohlcv_at_low(date_str: str, close: float, vol_mult: float = 1.0) -> dict:
    """Build one OHLCV record that closed_at_low (close is at/near the low)."""
    low = close * 0.99
    return {
        "time": date_str,
        "open": close * 1.03,
        "high": close * 1.05,
        "low": low,
        "close": low,  # close == low → closed_at_low == True
        "volume": int(1_000_000 * vol_mult),
    }


def _rsi_record(date_str: str, rsi: float) -> dict:
    return {"date": date_str, "rsi": rsi, "macd": {}, "sma20": 35.0, "sma50": 34.0}


def _mock_ohlcv_result(ticker: str, records: list[dict]) -> dict:
    return {ticker.upper(): {"data": records, "count": len(records)}}


def _mock_rsi_result(records: list[dict]) -> dict:
    return {"data": records}


def _patch_stats(ohlcv_result: dict, rsi_result: dict):
    """Context manager that patches fetch_history_batch, fetch_technicals_history,
    and pins `datetime.now()` inside the statistics module to TEST_NOW so
    days_back cutoffs do not drift as the wall clock advances.
    """
    stack = ExitStack()
    stack.enter_context(
        patch("shared.api.statistics.fetch_history_batch", AsyncMock(return_value=ohlcv_result))
    )
    stack.enter_context(
        patch(
            "shared.api.statistics.fetch_technicals_history",
            AsyncMock(return_value=rsi_result),
        )
    )
    fake_dt = MagicMock(wraps=datetime)
    fake_dt.now = MagicMock(return_value=TEST_NOW)
    stack.enter_context(patch("shared.api.statistics.datetime", fake_dt))
    return stack
