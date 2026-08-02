from __future__ import annotations

"""Technicals — reads directly from vnstock API.

Thin adapter over data/technicals.fetch_technicals_async().
Accepts a flat list of tickers instead of the watchlist dict format.

Replaces:
- daily_technicals table reads in pipeline consumers → get_technicals()
- daily_levels table reads → get_ticker_technicals()
- daily_prices table reads → get_ticker_technicals()
- v_latest_technicals SQL view (current indicators per ticker)

Same return shapes as old neon/technicals.py functions — consumers change import only.
"""

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

from data.technicals import fetch_technicals_async

if TYPE_CHECKING:
    from pipeline.types import FlatTechnicalsRow


def _flatten_row(row: dict) -> dict:
    """Flatten nested `supertrend`/`adx` dicts into top-level scalars.

    Every `get_technicals()` consumer reads the flat shape — `adx`,
    `adx_dmp`, `adx_dmn`, `supertrend_direction`. The producer at
    `data/technicals.py::fetch_technicals_async` always emits `supertrend`
    and `adx` as `dict | None`; this function assumes that contract and
    fails loud on any scalar it didn't produce itself (per CLAUDE.md).
    Error stubs carry a top-level `error` key and pass through unchanged.
    """
    if not isinstance(row, dict) or "error" in row:
        return row

    flat = dict(row)

    supertrend = flat.pop("supertrend", None) or {}
    flat["supertrend_direction"] = supertrend.get("direction")

    adx = flat.pop("adx", None) or {}
    flat["adx"] = adx.get("adx")
    flat["adx_dmp"] = adx.get("dmp")
    flat["adx_dmn"] = adx.get("dmn")
    # Surface the direction series at top level so consumers (trend_momentum
    # rule, briefing renderer) can read it alongside the scalar ADX value.
    flat["adx_series"] = adx.get("series")

    # Extract macd histogram direction series from the nested `macd` dict.
    # `macd` itself stays as its existing shape so scalar readers still work.
    macd = flat.get("macd")
    if isinstance(macd, dict):
        flat["macd_histogram_series"] = macd.get("histogram_series")

    flat.pop("bbands", None)
    flat.pop("stoch", None)

    return flat


async def get_technicals(tickers: list[str]) -> dict[str, FlatTechnicalsRow]:
    """Get full technical analysis for a list of tickers.

    Returns {ticker: {rsi, ma20, ma50, macd, macd_signal, macd_histogram,
                      atr, supertrend_direction, adx, adx_dmp, adx_dmn,
                      levels, pattern, trend, analysis,
                      closed_at_low, volume_vs_avg, price_vs_ma20, price_vs_ma50}}

    Flat canonical shape — `supertrend` and `adx` are flattened to top-level
    scalars (`supertrend_direction`, `adx`, `adx_dmp`, `adx_dmn`) so consumers
    like `context_blocks_ticker` can run `adx >= 25` without a TypeError. All
    `get_technicals()` callers must read the flat shape.
    """
    if not tickers:
        return {}

    watchlist = {"all": [t.upper() for t in tickers]}
    raw = await fetch_technicals_async(watchlist)
    return cast(
        "dict[str, FlatTechnicalsRow]",
        {ticker: _flatten_row(row) for ticker, row in raw.items()},
    )


def _calc_volume_context(bars: list[dict]) -> dict:
    """Compute volume_context from recent OHLCV bars (API format).

    bars: list of {open, high, low, close, volume} dicts, newest last.
    Mirrors neon/technicals._calculate_volume_context().
    """
    if not bars or len(bars) < 2:
        return {"volume_trend": "unknown", "bounce_confirmed": None, "prior_down_volume": None}

    # newest bar is last
    today = bars[-1]
    today_volume = int(today.get("volume") or 0)
    today_up = (today.get("close") or 0) > (today.get("open") or 0)

    recent = list(reversed(bars[-3:]))  # [today, yesterday, day_before]
    volumes = [int(r.get("volume") or 0) for r in recent]

    if len(volumes) >= 3:
        if volumes[0] > volumes[1] > volumes[2]:
            volume_trend = "increasing"
        elif volumes[0] < volumes[1] < volumes[2]:
            volume_trend = "decreasing"
        else:
            volume_trend = "stable"
    elif len(volumes) == 2:
        volume_trend = "increasing" if volumes[0] > volumes[1] else "decreasing"
    else:
        volume_trend = "unknown"

    prior_down_volume = None
    bounce_confirmed = None

    # Walk backwards (skip today) to find last down-day
    for bar in reversed(bars[:-1]):
        close = bar.get("close") or 0
        open_price = bar.get("open") or 0
        if close < open_price:
            prior_down_volume = int(bar.get("volume") or 0)
            break

    if today_up and prior_down_volume is not None:
        bounce_confirmed = today_volume > prior_down_volume

    return {
        "volume_trend": volume_trend,
        "bounce_confirmed": bounce_confirmed,
        "prior_down_volume": prior_down_volume,
    }


def _merge_ticker_technicals(ticker: str, tech_map: dict, price_map: dict) -> dict:
    """Merge technicals + price history for one ticker into the flat result dict.

    Splices OHLCV from the price map and computes volume_context. Flattening
    of `supertrend`/`adx` already happened in `get_technicals()` upstream, so
    the input `tech_map[ticker]` is already the flat canonical shape. Returns
    `{"ticker": X, "error": "..."}` if no technicals present.
    """
    if not tech_map or ticker not in tech_map:
        return {"ticker": ticker, "error": f"No technicals data for {ticker}"}

    result = dict(tech_map[ticker])
    result["ticker"] = ticker

    # Merge OHLCV from price history (API prices in thousands VND → convert to VND)
    ticker_prices = price_map.get(ticker, {})
    bars = ticker_prices.get("data", []) if isinstance(ticker_prices, dict) else []
    if bars:
        latest = bars[-1]
        result["close"] = int(round((latest.get("close") or 0) * 1000))
        result["open"] = int(round((latest.get("open") or 0) * 1000))
        result["high"] = int(round((latest.get("high") or 0) * 1000))
        result["low"] = int(round((latest.get("low") or 0) * 1000))
        result["volume"] = int(latest.get("volume") or 0)
        result["volume_context"] = _calc_volume_context(bars[-5:])
        # Extract last price date for staleness detection (CLAUDE.md rule 17)
        bar_time = latest.get("time")
        if bar_time:
            result["data_date"] = str(bar_time)[:10]
    else:
        result["volume_context"] = {
            "volume_trend": "unknown",
            "bounce_confirmed": None,
            "prior_down_volume": None,
        }

    return result


async def get_batch_ticker_technicals(tickers: list[str]) -> dict[str, FlatTechnicalsRow]:
    """Get full technicals + OHLCV + volume_context for a batch of tickers.

    True batch: TWO parallel API calls total (technicals + history), regardless
    of ticker count. Previously: 3N calls (1 technicals + 2 history per ticker).

    Partial-success contract: returns dict keyed by uppercased ticker. Missing
    tickers map to `{"ticker": X, "error": "No technicals data for X"}`.
    """
    from shared.vnstock_client import fetch_history_batch

    if not tickers:
        return {}

    from shared.rules.trend_momentum import derive_momentum_signals

    normalized = [ticker.upper() for ticker in tickers]
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

    tech_map, price_map = await asyncio.gather(
        get_technicals(normalized),
        fetch_history_batch(normalized, start=start, end=end),
    )

    merged: dict[str, FlatTechnicalsRow] = {
        ticker: cast("FlatTechnicalsRow", _merge_ticker_technicals(ticker, tech_map, price_map))
        for ticker in normalized
    }

    # Derive trend-momentum direction signals once per ticker so briefing
    # renderer and picks composer consume a shared, deterministic value.
    # Error rows (carrying "error" key) are skipped — no signals to derive.
    for row in merged.values():
        if row.get("error"):
            continue
        row["momentum_signals"] = derive_momentum_signals(row)

    return merged


async def get_ticker_technicals(ticker: str) -> FlatTechnicalsRow:
    """Get full technicals + OHLCV + volume_context for a single ticker.

    Delegates to `get_batch_ticker_technicals([ticker])` so single-ticker callers
    get the same partial-success contract. Still 2 API calls (unavoidable).
    """
    batch = await get_batch_ticker_technicals([ticker])
    return batch[ticker.upper()]
