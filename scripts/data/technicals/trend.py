"""Trend classification + analysis-text generator."""

from __future__ import annotations

import pandas as pd


def classify_trend(df: pd.DataFrame, ma20: float | None, ma50: float | None) -> dict:
    """Classify trend direction, strength, and momentum."""
    close = df["close"].iloc[-1]

    if ma20 is None or ma50 is None:
        direction = "UNKNOWN"
    elif close > ma20 and ma20 > ma50:
        direction = "UPTREND"
    elif close < ma20 and ma20 < ma50:
        direction = "DOWNTREND"
    else:
        direction = "SIDEWAYS"

    if ma20 and ma20 > 0:
        ma20_dist = abs(close - ma20) / ma20 * 100
        if ma20_dist > 5:
            strength = "strong"
        elif ma20_dist > 2:
            strength = "moderate"
        else:
            strength = "weak"
    else:
        strength = "unknown"

    if len(df) >= 5:
        last5 = df.tail(5)
        green_count = (last5["close"] > last5["open"]).sum()
        if green_count >= 4:
            momentum = "bullish"
        elif green_count <= 1:
            momentum = "bearish"
        else:
            momentum = "neutral"
    else:
        momentum = "unknown"

    return {
        "trend": direction,
        "strength": strength,
        "momentum": momentum,
    }


def generate_analysis_text(
    ticker: str,
    price: float,
    trend: dict,
    pattern: dict,
    levels: dict,
    rsi: float | None,
    macd_hist: float | None,
) -> str:
    """Generate natural language analysis summary for LLM consumption."""
    parts = []

    parts.append(f"{ticker}: {trend['trend']} ({trend['strength']})")

    if levels.get("nearest_support"):
        dist_support = (price - levels["nearest_support"]) / price * 100
        parts.append(f"Price {dist_support:.1f}% above support {levels['nearest_support']}")
    elif levels.get("nearest_resistance"):
        parts.append(f"Price below key supports, next resistance {levels['nearest_resistance']}")

    if pattern.get("pattern"):
        parts.append(f"Pattern: {pattern['pattern']} ({pattern['signal']})")

    if rsi is not None:
        if rsi < 30:
            parts.append(f"RSI {rsi:.0f} OVERSOLD")
        elif rsi > 70:
            parts.append(f"RSI {rsi:.0f} OVERBOUGHT")
        elif 40 <= rsi <= 50:
            parts.append(f"RSI {rsi:.0f} neutral zone")
        elif rsi < 40:
            parts.append(f"RSI {rsi:.0f} approaching oversold")
        else:
            parts.append(f"RSI {rsi:.0f}")

    parts.append(f"Momentum: {trend['momentum']}")

    if macd_hist is not None:
        if macd_hist > 0:
            parts.append("MACD bullish")
        else:
            parts.append("MACD bearish")

    if levels.get("range_20d_high") and levels.get("range_20d_low"):
        parts.append(f"Range: {levels['range_20d_low']}-{levels['range_20d_high']}")

    return ". ".join(parts)
