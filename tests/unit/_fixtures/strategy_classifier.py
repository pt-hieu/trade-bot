"""Shared make_technicals fixture for strategy_classifier test splits."""

from __future__ import annotations


def make_technicals(
    close: float = 50_000,
    rsi: float | None = 50.0,
    ma20: float | None = 49_000,
    ma50: float | None = 48_000,
    volume_vs_avg: float | None = 1.2,
    trend_direction: str = "SIDEWAYS",
    swing_low: float | None = 45_000,
    nearest_support: float | None = 46_000,
    nearest_resistance: float | None = 55_000,
) -> dict:
    """Build a technicals dict with sensible defaults. Override only what matters for the test."""
    return {
        "close": close,
        "rsi": rsi,
        "ma20": ma20,
        "ma50": ma50,
        "volume_vs_avg": volume_vs_avg,
        "trend": {"trend": trend_direction, "strength": "moderate", "momentum": "neutral"},
        "levels": {
            "swing_low": swing_low,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
        },
    }
