"""Async + sync orchestrators that fetch OHLCV+TA and assemble per-ticker payloads."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from shared.neon._utils import safe_round

from ._numpy import _sanitize_numpy
from .levels import calculate_range_levels, detect_swing_points, find_nearest_levels
from .patterns import (
    calculate_closed_at_low,
    calculate_volume_vs_avg,
    detect_candlestick_patterns,
)
from .trend import classify_trend, generate_analysis_text

# Levels keys whose values arrive from find_nearest_levels / swing-point /
# range computations in thousand-VND and must be multiplied ×1000 to land
# downstream in canonical VND-integer units (rule 18). Hoisted to module
# scope so structural-completeness tests can assert the producer's key set
# is a subset of this allowlist — preventing the SWI-125 regression where
# SWI-289 added nearest_swing_low / nearest_swing_target to find_nearest_levels
# but the normalizer's local list was not updated.
_PRICE_LEVEL_KEYS: tuple[str, ...] = (
    "swing_high",
    "swing_low",
    "range_20d_high",
    "range_20d_low",
    "nearest_support",
    "nearest_resistance",
    "nearest_swing_low",
    "nearest_swing_target",
)


async def fetch_technicals_async(watchlist: dict, end_date: str | None = None) -> dict:
    """Fetch technical indicators for watchlist stocks via vnstock API.

    Uses vnstock_ta on Lightsail server for ATR, SUPERTREND, ADX, BBANDS, STOCH.
    Keeps custom logic for swing points, patterns, trend classification.
    """
    from shared.market_calendar import last_trading_day
    from shared.vnstock_client import fetch_history_batch, fetch_technicals_batch

    print("Fetching technicals via vnstock API (vnstock_ta)...")

    all_stocks = []
    for tickers in watchlist.values():
        all_stocks.extend(tickers)

    if end_date is None:
        end_date = last_trading_day().strftime("%Y-%m-%d")
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=100)).strftime(
        "%Y-%m-%d"
    )

    try:
        history_results = await fetch_history_batch(
            symbols=all_stocks,
            source="VCI",
            start=start_date,
            end=end_date,
            interval="1D",
        )

        ta_results = await fetch_technicals_batch(
            symbols=all_stocks,
            source="VCI",
            start=start_date,
            end=end_date,
        )

        technicals_data = {}

        for symbol in all_stocks:
            try:
                history_data = history_results.get(symbol, {})
                ta_data = ta_results.get(symbol, {})

                if "error" in history_data:
                    raise ValueError(history_data["error"])
                if "error" in ta_data:
                    raise ValueError(ta_data["error"])

                df = pd.DataFrame(history_data.get("data", []))

                if df.empty or len(df) < 14:
                    raise ValueError("Insufficient data")

                latest_close = df["close"].iloc[-1]

                rsi_val = safe_round(ta_data.get("rsi"), 2)
                rsi_series_val = ta_data.get("rsi_series")
                ma20_val = safe_round(ta_data.get("sma20"), 2)
                ma50_val = safe_round(ta_data.get("sma50"), 2)

                macd_data = ta_data.get("macd", {})
                macd_val = safe_round(macd_data.get("MACD"), 2)
                macd_signal_val = safe_round(macd_data.get("signal"), 2)
                macd_hist_val = safe_round(macd_data.get("histogram"), 2)
                macd_hist_series_val = macd_data.get("histogram_series")

                atr_val = safe_round(ta_data.get("atr"), 4)

                supertrend_data = ta_data.get("supertrend", {})
                supertrend_val = None
                if supertrend_data:
                    supertrend_val = {
                        "value": safe_round(supertrend_data.get("value"), 4),
                        "direction": supertrend_data.get("direction"),
                        "lower": safe_round(supertrend_data.get("lower"), 4),
                        "upper": safe_round(supertrend_data.get("upper"), 4),
                    }

                adx_data = ta_data.get("adx", {})
                adx_val = None
                if adx_data:
                    adx_val = {
                        "adx": safe_round(adx_data.get("adx"), 2),
                        "dmp": safe_round(adx_data.get("dmp"), 2),
                        "dmn": safe_round(adx_data.get("dmn"), 2),
                        "series": adx_data.get("series"),
                    }

                bbands_data = ta_data.get("bbands", {})
                bbands_val = None
                if bbands_data:
                    bbands_val = {
                        "lower": safe_round(bbands_data.get("lower"), 4),
                        "middle": safe_round(bbands_data.get("middle"), 4),
                        "upper": safe_round(bbands_data.get("upper"), 4),
                        "bandwidth": safe_round(bbands_data.get("bandwidth"), 4),
                        "percent": safe_round(bbands_data.get("percent"), 4),
                    }

                stoch_data = ta_data.get("stoch", {})
                stoch_val = None
                if stoch_data:
                    stoch_val = {
                        "k": safe_round(stoch_data.get("k"), 2),
                        "d": safe_round(stoch_data.get("d"), 2),
                    }

                swing_points = detect_swing_points(df, window=5)
                range_levels = calculate_range_levels(df, window=20)

                latest = df.iloc[-1]
                closed_at_low = calculate_closed_at_low(
                    high=float(latest["high"]),
                    low=float(latest["low"]),
                    close=float(latest["close"]),
                )
                volume_vs_avg = calculate_volume_vs_avg(df, window=20)

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

                analysis_text = generate_analysis_text(
                    ticker=symbol,
                    price=latest_close,
                    trend=trend,
                    pattern=pattern,
                    levels=levels,
                    rsi=rsi_val,
                    macd_hist=macd_hist_val,
                )

                # Normalize price-based values from thousands VND to VND (rule 18).
                # Allowlist defined at module scope (see _PRICE_LEVEL_KEYS above).
                for key in _PRICE_LEVEL_KEYS:
                    if key in levels and isinstance(levels[key], (int, float)):
                        levels[key] = int(round(levels[key] * 1000))

                if ma20_val is not None:
                    ma20_val = int(round(ma20_val * 1000))
                if ma50_val is not None:
                    ma50_val = int(round(ma50_val * 1000))

                latest_close = int(round(latest_close * 1000))

                if atr_val is not None:
                    atr_val = round(atr_val * 1000, 2)

                if supertrend_val:
                    for st_key in ("value", "lower", "upper"):
                        if supertrend_val.get(st_key) is not None:
                            supertrend_val[st_key] = round(supertrend_val[st_key] * 1000, 2)

                if bbands_val:
                    for bb_key in ("lower", "middle", "upper"):
                        bb_raw = bbands_val.get(bb_key)
                        if bb_raw is not None:
                            bbands_val[bb_key] = round(bb_raw * 1000, 2)

                technicals_data[symbol] = _sanitize_numpy(
                    {
                        "rsi": rsi_val,
                        "rsi_series": rsi_series_val,
                        "ma20": ma20_val,
                        "ma50": ma50_val,
                        "macd": macd_val,
                        "macd_signal": macd_signal_val,
                        "macd_histogram": macd_hist_val,
                        "macd_histogram_series": macd_hist_series_val,
                        "price_vs_ma20": "above"
                        if ma20_val and latest_close > ma20_val
                        else "below",
                        "price_vs_ma50": "above"
                        if ma50_val and latest_close > ma50_val
                        else "below",
                        "atr": atr_val,
                        "supertrend": supertrend_val,
                        "adx": adx_val,
                        "bbands": bbands_val,
                        "stoch": stoch_val,
                        "close": latest_close,
                        "levels": levels if levels else None,
                        "pattern": pattern,
                        "trend": trend,
                        "analysis": analysis_text,
                        "closed_at_low": closed_at_low,
                        "volume_vs_avg": volume_vs_avg,
                    }
                )

                adx_str = f"ADX={adx_val['adx']}" if adx_val else "ADX=N/A"
                st_dir = supertrend_val.get("direction") if supertrend_val else "N/A"
                vol_str = f"Vol={volume_vs_avg}x" if volume_vs_avg else "Vol=N/A"
                low_str = "LOW" if closed_at_low else ""
                print(
                    f"  {symbol}: RSI={rsi_val}, {adx_str}, ST={st_dir}, {vol_str} {low_str}".strip()
                )

            except Exception as e:
                print(f"  {symbol}: Error - {e}")
                technicals_data[symbol] = {"error": str(e)}

        return technicals_data

    except Exception as e:
        print(f"vnstock API error in fetch_technicals: {e}")
        import traceback

        traceback.print_exc()
        return {}


def fetch_technicals(watchlist: dict, end_date: str | None = None) -> dict:
    """Sync wrapper for fetch_technicals_async."""
    import asyncio

    return asyncio.run(fetch_technicals_async(watchlist, end_date=end_date))
