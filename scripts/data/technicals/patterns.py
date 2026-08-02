"""Candlestick patterns + per-bar volume / close-position signals."""

from __future__ import annotations

import pandas as pd


def calculate_closed_at_low(high: float, low: float, close: float) -> bool:
    """Determine if price closed in the bottom 10% of day's range.

    This is a bearish signal indicating selling pressure into the close.
    Used for statistical analysis of distribution days and reversal patterns.
    """
    day_range = high - low
    if day_range == 0:
        return False
    position_in_range = (close - low) / day_range
    return bool(position_in_range <= 0.10)


def calculate_volume_vs_avg(df: pd.DataFrame, window: int = 20) -> float | None:
    """Calculate ratio of today's volume to N-day average volume.

    Values > 1.5 indicate high volume (potential breakout/capitulation).
    Values < 0.5 indicate low volume (weak move, low conviction).
    """
    if len(df) < window:
        return None

    avg_vol = df["volume"].tail(window).mean()
    if avg_vol == 0:
        return None

    today_vol = df["volume"].iloc[-1]
    return float(round(today_vol / avg_vol, 2))


def detect_candlestick_patterns(df: pd.DataFrame) -> dict:
    """Detect candlestick patterns in recent candles.

    Identifies: hammer, inverted_hammer, doji, bullish_engulfing, bearish_engulfing.
    """
    if len(df) < 3:
        return {"pattern": None, "signal": None}

    c = df.iloc[-1]
    p = df.iloc[-2]

    body = abs(c["close"] - c["open"])
    range_ = c["high"] - c["low"]

    if range_ == 0:
        return {"pattern": None, "signal": None}

    lower_wick = min(c["open"], c["close"]) - c["low"]
    upper_wick = c["high"] - max(c["open"], c["close"])

    # Hammer: small body at top, long lower wick (2x body)
    if body > 0 and body < range_ * 0.3 and lower_wick > body * 2:
        return {"pattern": "hammer", "signal": "bullish_reversal"}

    # Inverted Hammer: small body at bottom, long upper wick
    if body > 0 and body < range_ * 0.3 and upper_wick > body * 2:
        return {"pattern": "inverted_hammer", "signal": "bullish_reversal"}

    # Doji: open ≈ close (very small body)
    if body < range_ * 0.1:
        return {"pattern": "doji", "signal": "indecision"}

    # Bullish engulfing
    if (
        c["close"] > c["open"]
        and p["close"] < p["open"]
        and c["open"] <= p["close"]
        and c["close"] >= p["open"]
    ):
        return {"pattern": "bullish_engulfing", "signal": "bullish_reversal"}

    # Bearish engulfing
    if (
        c["close"] < c["open"]
        and p["close"] > p["open"]
        and c["open"] >= p["close"]
        and c["close"] <= p["open"]
    ):
        return {"pattern": "bearish_engulfing", "signal": "bearish_reversal"}

    return {"pattern": None, "signal": None}
