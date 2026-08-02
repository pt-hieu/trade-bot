"""Async ticker-data fetchers (batch + single + realtime)."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import cast

import logfire
import pandas as pd

from .prose import _check_staleness, _format_technicals_prose, is_structural_uptrend
from .setup_calc import _enrich_with_setup_and_prose, compute_setup_from_levels

logger = logging.getLogger(__name__)

# Module-level cache for real-time fetches within session
_REALTIME_CACHE: dict[str, dict] = {}

# SWI-354: cap per-ticker fallback fanout to avoid amplifying load on a
# degraded upstream. Above this size, batch failure short-circuits to
# blanket error rows rather than firing N concurrent single-ticker calls.
_MAX_FALLBACK_FANOUT = 20


def _synthetic_error_row(ticker: str, scan_date: date | None) -> dict:
    """Synthetic error row used when no real technicals can be fetched."""
    return {
        "ticker": ticker,
        "error": f"No data for {ticker} on {scan_date}",
        "prose": f"{ticker}: No data available for {scan_date}.",
    }


async def get_ticker_data_async(
    ticker: str,
    scan_date: date | None = None,
    risk_regime: str | None = None,
) -> dict:
    """Get ticker technicals — single-ticker wrapper over the batch path."""
    batch = await get_batch_ticker_data_async([ticker], scan_date, risk_regime=risk_regime)
    return batch[ticker.upper()]


async def get_batch_ticker_data_async(
    tickers: list[str],
    scan_date: date | None = None,
    risk_regime: str | None = None,
) -> dict[str, dict]:
    """Get technicals + trade_setup + price_action for a batch of tickers.

    Performs ONE batch technicals fetch (2 HTTP calls total regardless of
    ticker count), then fans out `get_price_action_context` concurrently per
    ticker. SWI-42 batch price_action seam.
    """
    from shared.api.technicals import get_batch_ticker_technicals

    # SWI-301: canonical batch fetcher for 20d relative strength.
    # agents/tools/enrichment.py wraps this for the LLM tool surface;
    # do not introduce a third caller.
    from shared.neon.enrichment import get_relative_strength

    from ..price_action import get_price_action_context

    if not tickers:
        return {}

    normalized = [ticker.upper() for ticker in tickers]

    relative_strength_task = asyncio.create_task(
        get_relative_strength(normalized, scan_date or date.today())
    )

    fallback_used = False
    fanout_skipped = False
    batch_error_type: str | None = None
    try:
        batch = await get_batch_ticker_technicals(normalized)
    except Exception as error:
        # SWI-356: surface the actual exception class so SWI-357 retry policy
        # can be tuned with evidence. logger.exception already routes to
        # logfire — no separate logfire.exception call needed.
        batch_error_type = type(error).__name__
        logger.exception("get_batch_ticker_technicals failed (falling back per-ticker)")

        # SWI-354: post-SWI-357 retry exhaustion / non-5xx exception means
        # all batch attempts failed — fan out to per-ticker calls so a
        # single bad row no longer collapses the whole scan. Capped at
        # _MAX_FALLBACK_FANOUT to avoid amplifying load on a degraded upstream.
        if len(normalized) > _MAX_FALLBACK_FANOUT:
            relative_strength_task.cancel()
            await asyncio.gather(relative_strength_task, return_exceptions=True)
            fanout_skipped = True
            logfire.info(
                "batch_technicals_fetch",
                fallback_used=False,
                fanout_skipped=fanout_skipped,
                fanout_size=len(normalized),
                error_type=batch_error_type,
            )
            return {ticker: _synthetic_error_row(ticker, scan_date) for ticker in normalized}

        from shared.api.technicals import get_ticker_technicals

        async def _per_ticker(ticker: str) -> tuple[str, dict | None]:
            try:
                return ticker, cast(dict, await get_ticker_technicals(ticker))
            except Exception as per_ticker_error:
                logger.warning("per-ticker fallback failed for %s: %s", ticker, per_ticker_error)
                return ticker, None

        per_ticker_results = await asyncio.gather(*[_per_ticker(t) for t in normalized])
        batch = {}
        for ticker, result in per_ticker_results:
            if result is None or result.get("error"):
                batch[ticker] = _synthetic_error_row(ticker, scan_date)
            else:
                batch[ticker] = result
        fallback_used = True

    logfire.info(
        "batch_technicals_fetch",
        fallback_used=fallback_used,
        fanout_skipped=fanout_skipped,
        fanout_size=len(normalized),
        error_type=batch_error_type,
    )

    for ticker in normalized:
        result = batch.get(ticker)
        if result is None or "error" in result:
            continue
        _enrich_with_setup_and_prose(ticker, cast(dict, result), risk_regime=risk_regime)

    async def _fetch_pa(ticker: str) -> tuple[str, dict | None]:
        result = batch.get(ticker)
        if result is None or "error" in result:
            return ticker, None
        close = result.get("close", 0)
        if not close:
            return ticker, None
        try:
            return ticker, await get_price_action_context(ticker, scan_date, close)
        except Exception as error:
            logger.warning("get_price_action_context failed for %s: %s", ticker, error)
            return ticker, None

    pa_results = await asyncio.gather(*[_fetch_pa(ticker) for ticker in normalized])
    for ticker, pa in pa_results:
        if pa and pa.get("classification") != "NORMAL":
            batch[ticker]["price_action"] = pa

    try:
        relative_strength_by_ticker = await relative_strength_task
    except Exception as exception:
        logger.warning(
            "get_relative_strength batch failed (%d tickers): %s — rs_20d falls through to neutral 1.0",
            len(normalized),
            exception,
        )
        relative_strength_by_ticker = {}

    for ticker in normalized:
        entry = batch.get(ticker)
        if entry is None or "error" in entry:
            continue
        entry["rs_20d"] = relative_strength_by_ticker.get(ticker)

    return cast(dict[str, dict], batch)


async def tool_get_technicals(ticker: str, scan_date: date | None = None) -> str:
    """Get technical analysis for a ticker. For LLM agents — returns prose."""
    result = await get_ticker_data_async(ticker=ticker, scan_date=scan_date)
    if "error" in result:
        return f"INSUFFICIENT DATA for {ticker}: {result['error']}. Do NOT analyze this ticker."

    prose = result.get("prose", str(result))

    stale_warning = _check_staleness(result, scan_date)
    if stale_warning:
        prose = f"WARNING STALE DATA: {stale_warning}\n{prose}"
        result["_stale"] = True

    return prose


async def tool_get_technicals_realtime(ticker: str) -> str:
    """Get real-time technicals for a ticker not in daily scan. Returns prose."""
    result = await fetch_technicals_realtime_async(ticker)
    return result.get("prose", str(result))


async def fetch_technicals_realtime_async(ticker: str) -> dict:
    """Fetch real-time technicals via vnstock API for candidates not in daily scan."""
    from shared.vnstock_client import fetch_history

    ticker = ticker.upper()

    if ticker in _REALTIME_CACHE:
        return _REALTIME_CACHE[ticker]

    try:
        from data.technicals import (
            calculate_range_levels,
            classify_trend,
            detect_candlestick_patterns,
            detect_swing_points,
            find_nearest_levels,
            generate_analysis_text,
        )

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")

        result = await fetch_history(
            symbol=ticker,
            source="VCI",
            start=start_date,
            end=end_date,
            interval="1D",
        )

        if "error" in result:
            error_result = {
                "ticker": ticker,
                "error": result["error"],
                "source": "realtime",
                "prose": f"{ticker}: {result['error']}",
            }
            _REALTIME_CACHE[ticker] = error_result
            return error_result

        df = pd.DataFrame(result.get("data", []))

        if df.empty or len(df) < 14:
            error_result = {
                "ticker": ticker,
                "error": "Insufficient data",
                "source": "realtime",
                "prose": f"{ticker}: Insufficient historical data.",
            }
            _REALTIME_CACHE[ticker] = error_result
            return error_result

        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        ma20 = df["close"].rolling(window=20).mean()
        ma50 = df["close"].rolling(window=50).mean()

        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()

        latest = df.iloc[-1]
        latest_close = latest["close"]

        ma20_val = float(round(ma20.iloc[-1], 2)) if not pd.isna(ma20.iloc[-1]) else None  # type: ignore[reportAttributeAccessIssue]
        ma50_val = float(round(ma50.iloc[-1], 2)) if not pd.isna(ma50.iloc[-1]) else None  # type: ignore[reportAttributeAccessIssue]

        swing_points = detect_swing_points(df, window=5)
        range_levels = calculate_range_levels(df, window=20)

        levels = {}
        levels.update(swing_points)
        levels.update(range_levels)

        nearest = find_nearest_levels(
            price=latest_close,
            ma20=ma20_val,
            ma50=ma50_val,
            swing_high=swing_points.get("swing_high"),
            swing_low=swing_points.get("swing_low"),
            range_high=range_levels.get("range_20d_high"),
            range_low=range_levels.get("range_20d_low"),
        )
        levels.update(nearest)

        pattern = detect_candlestick_patterns(df)
        trend = classify_trend(df, ma20_val, ma50_val)

        rsi_val = float(round(rsi.iloc[-1], 2)) if not pd.isna(rsi.iloc[-1]) else None  # type: ignore[reportAttributeAccessIssue]
        macd_val = float(round(macd.iloc[-1], 2)) if not pd.isna(macd.iloc[-1]) else None  # type: ignore[reportAttributeAccessIssue]
        signal_val = float(round(signal.iloc[-1], 2)) if not pd.isna(signal.iloc[-1]) else None  # type: ignore[reportAttributeAccessIssue]
        macd_hist = (
            float(round((macd.iloc[-1] - signal.iloc[-1]), 2)) if macd_val and signal_val else None
        )

        analysis_text = generate_analysis_text(
            ticker=ticker,
            price=latest_close,
            trend=trend,
            pattern=pattern,
            levels=levels,
            rsi=rsi_val,
            macd_hist=macd_hist,
        )

        levels_normalized = None
        if levels:
            levels_normalized = levels.copy()
            for key in [
                "swing_high",
                "swing_low",
                "range_20d_high",
                "range_20d_low",
                "nearest_support",
                "nearest_resistance",
            ]:
                if key in levels_normalized and isinstance(levels_normalized[key], (int, float)):
                    levels_normalized[key] = levels_normalized[key] * 1000

        result = {
            "ticker": ticker,
            "close": latest_close * 1000,
            "open": latest["open"] * 1000,
            "high": latest["high"] * 1000,
            "low": latest["low"] * 1000,
            "volume": int(latest["volume"]) if "volume" in latest else None,
            "date": str(latest.get("time", df.index[-1]))[:10],
            "rsi": rsi_val,
            "ma20": ma20_val * 1000 if ma20_val else None,
            "ma50": ma50_val * 1000 if ma50_val else None,
            "macd": macd_val,
            "macd_signal": signal_val,
            "macd_histogram": macd_hist,
            "price_vs_ma20": "above" if latest_close > ma20.iloc[-1] else "below",  # type: ignore[reportAttributeAccessIssue]
            "price_vs_ma50": "above" if len(df) >= 50 and latest_close > ma50.iloc[-1] else "below",  # type: ignore[reportAttributeAccessIssue]
            "levels": levels_normalized,
            "pattern": pattern,
            "trend": trend,
            "analysis": analysis_text,
            "source": "realtime",
        }

        result["prose"] = _format_technicals_prose(result)

        _REALTIME_CACHE[ticker] = result
        return result

    except Exception as e:
        error_result = {"ticker": ticker, "error": f"Failed to fetch: {e}", "source": "realtime"}
        error_result["prose"] = f"{ticker}: Failed to fetch real-time data."
        _REALTIME_CACHE[ticker] = error_result
        return error_result


def _extract_trade_setup(ticker: str, data: dict) -> dict:
    """Pull the trade_setup dict out of a single enriched ticker result."""
    if "error" in data:
        return {"ticker": ticker, "valid": False, "error": data["error"]}

    if "trade_setup" in data:
        return data["trade_setup"]

    levels = data.get("levels") or {}
    close = data.get("close") or 0
    return compute_setup_from_levels(
        levels,
        close,
        ticker,
        structural_uptrend=is_structural_uptrend(data),
        atr=data.get("atr"),
    )


async def compute_trade_setup_async(
    ticker: str,
    scan_date: date | None = None,
) -> dict:
    """Compute deterministic Entry/Stop/Target/R:R for a single ticker."""
    try:
        data = await get_ticker_data_async(ticker, scan_date)
        return _extract_trade_setup(ticker, data)
    except Exception as exception:
        logger.warning("compute_trade_setup_async(%s) failed: %s", ticker, exception)
        return {"ticker": ticker, "valid": False, "error": str(exception)}


async def compute_batch_trade_setup_async(
    tickers: list[str],
    scan_date: date | None = None,
) -> dict[str, dict]:
    """Compute Entry/Stop/Target/R:R for a batch of tickers in one fetch."""
    try:
        batch = await get_batch_ticker_data_async(tickers, scan_date)
    except Exception as exception:
        logger.warning("compute_batch_trade_setup_async failed: %s", exception)
        return {
            ticker.upper(): {"ticker": ticker.upper(), "valid": False, "error": str(exception)}
            for ticker in tickers
        }

    return {
        ticker.upper(): _extract_trade_setup(ticker.upper(), batch.get(ticker.upper(), {}))
        for ticker in tickers
    }
