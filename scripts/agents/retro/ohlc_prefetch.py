"""OHLC pre-fetch wrapper for ATR_TRAIL PENDING resolution.

Thin filter over ``shared.api.prices.get_ohlc_series`` — identifies ATR_TRAIL
recs from the batch, computes the lookback window, and delegates to the
canonical fetcher. Price-unit conversion (thousands VND → VND int) lives
inside ``get_ohlc_series`` via ``shared.units.thousands_to_vnd``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from shared.api.prices import get_ohlc_series
from shared.rules.exit_strategy import ATR_TRAIL_STRATEGIES

logger = logging.getLogger(__name__)

_DEFAULT_LOOKBACK_TRADING_DAYS = 20


async def prefetch_exit_series(
    recs: list[dict],
    today: date,
    lookback_trading_days: int = _DEFAULT_LOOKBACK_TRADING_DAYS,
) -> dict[str, list[dict]]:
    """Return {ticker: [daily_bars]} for every ATR_TRAIL rec in ``recs``."""
    atr_tickers = {
        (rec.get("ticker") or "").upper()
        for rec in recs
        if (rec.get("strategy") or "").upper() in ATR_TRAIL_STRATEGIES
    }
    atr_tickers.discard("")
    if not atr_tickers:
        return {}

    start_candidates = [
        _coerce_date(rec.get("record_date")) for rec in recs if rec.get("record_date")
    ]
    earliest_entry = min((d for d in start_candidates if d is not None), default=today)
    start = earliest_entry - timedelta(days=lookback_trading_days)

    tickers_ordered = sorted(atr_tickers)
    logger.info(
        "ATR_TRAIL prefetch: %d tickers, start=%s, end=%s",
        len(tickers_ordered),
        start,
        today,
    )
    try:
        return await get_ohlc_series(
            tickers=tickers_ordered,
            start=start.isoformat(),
            end=today.isoformat(),
        )
    except Exception as error:  # noqa: BLE001 — surface, don't swallow
        logger.warning(
            "prefetch_exit_series failed for %d tickers: %s",
            len(tickers_ordered),
            error,
        )
        return {}


def _coerce_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            return None
    return None


__all__ = ["prefetch_exit_series"]
