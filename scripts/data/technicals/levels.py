"""Swing-point detection, N-day range, and nearest-level S/R search.

Output-field convention (SWI-3a — target derivation fix):
  - target-side reads `nearest_swing_target` (MA-free; max(swing_high, range_high))
  - stop-side reads `nearest_swing_low`     (MA-free; max(swing_low, range_low) below price)
  - breakout / bounce / prose / selloff-zone reads `nearest_resistance` / `nearest_support`
    (MA-INCLUSIVE; preserves trigger + narrative semantics).

Moving averages are dynamic trend-identification levels, NOT price targets.
Routing target consumers to MA-clipped resistance produced uniformly broken
R:R (~0.07-1.02), zero BUY recommendations for 47 trading days.
"""

from __future__ import annotations

import pandas as pd


def detect_swing_points(df: pd.DataFrame, window: int = 5) -> dict:
    """Detect swing highs and lows from price data.

    A swing low is when low[i] is lower than all lows in window before and after.
    A swing high is when high[i] is higher than all highs in window before and after.
    """
    if len(df) < window * 2 + 1:
        return {}

    highs = df["high"].values
    lows = df["low"].values

    dates = df["time"].values if "time" in df.columns else df.index.values

    swing_highs = []
    swing_lows = []

    for i in range(window, len(df) - window):
        is_swing_high = True
        for j in range(i - window, i + window + 1):
            if j != i and highs[j] >= highs[i]:
                is_swing_high = False
                break
        if is_swing_high:
            swing_highs.append((i, highs[i], dates[i]))

        is_swing_low = True
        for j in range(i - window, i + window + 1):
            if j != i and lows[j] <= lows[i]:
                is_swing_low = False
                break
        if is_swing_low:
            swing_lows.append((i, lows[i], dates[i]))

    result = {}

    if swing_highs:
        _, high_val, high_date = swing_highs[-1]
        result["swing_high"] = round(float(high_val), 2)
        result["swing_high_date"] = str(high_date)[:10]

    if swing_lows:
        _, low_val, low_date = swing_lows[-1]
        result["swing_low"] = round(float(low_val), 2)
        result["swing_low_date"] = str(low_date)[:10]

    # Provisional fallback: if current price broke below/above detected swings,
    # use recent extreme as provisional swing point (can't be confirmed yet
    # because the 5-bar window hasn't completed).
    current_low = float(lows[-1])
    current_high = float(highs[-1])

    if result.get("swing_low") and current_low < result["swing_low"]:
        recent_lows = lows[-window:]
        recent_dates = dates[-window:]
        min_idx = recent_lows.argmin()
        result["swing_low"] = round(float(recent_lows[min_idx]), 2)
        result["swing_low_date"] = str(recent_dates[min_idx])[:10]

    if result.get("swing_high") and current_high > result["swing_high"]:
        recent_highs = highs[-window:]
        recent_dates = dates[-window:]
        max_idx = recent_highs.argmax()
        result["swing_high"] = round(float(recent_highs[max_idx]), 2)
        result["swing_high_date"] = str(recent_dates[max_idx])[:10]

    return result


def calculate_range_levels(df: pd.DataFrame, window: int = 20) -> dict:
    """Calculate N-day high/low range levels."""
    if len(df) < window:
        return {}

    recent = df.tail(window)
    return {
        "range_20d_high": round(float(recent["high"].max()), 2),  # type: ignore[reportArgumentType]
        "range_20d_low": round(float(recent["low"].min()), 2),  # type: ignore[reportArgumentType]
    }


def find_nearest_levels(
    price: float,
    ma20: float | None,
    ma50: float | None,
    swing_high: float | None,
    swing_low: float | None,
    range_high: float | None,
    range_low: float | None,
) -> dict:
    """Find nearest support and resistance from available levels."""
    supports = []
    resistances = []

    for level in [ma20, ma50, swing_low, range_low]:
        if level is not None and level < price:
            supports.append(level)

    for level in [ma20, ma50, swing_high, range_high]:
        if level is not None and level > price:
            resistances.append(level)

    result = {}

    # Existing MA-inclusive levels — preserved for breakout / bounce /
    # prose / selloff-zone consumers (semantic: nearest level above/below
    # price regardless of structural-vs-dynamic origin).
    if supports:
        result["nearest_support"] = round(max(supports), 2)

    if resistances:
        result["nearest_resistance"] = round(min(resistances), 2)

    # MA-free target side (SWI-3a). Prefers the HIGHER of swing_high vs
    # range_20d_high so trades have real upside; absent when both are
    # missing (consumers fall through to MA-inclusive resistance OR honest
    # rejection rather than a tiny MA-clipped R:R).
    swing_targets = [
        level for level in [swing_high, range_high] if level is not None and level > price
    ]
    if swing_targets:
        result["nearest_swing_target"] = round(max(swing_targets), 2)

    # MA-free stop side (SWI-3a). Prefers the CLOSEST swing/range low below
    # price (mirrors the nearest_support `max()` semantic, MA-free). This
    # value is consumed as the entry-support; the stop derivation in
    # setup_calc.py applies its own buffer below the swing low.
    swing_lows = [level for level in [swing_low, range_low] if level is not None and level < price]
    if swing_lows:
        result["nearest_swing_low"] = round(max(swing_lows), 2)

    return result
