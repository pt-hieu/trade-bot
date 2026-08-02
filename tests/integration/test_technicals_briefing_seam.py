"""Integration test for the `get_technicals → format_ticker_briefing` seam.

Root cause of the 2026-04-20 Phase 2 collapse: `context_blocks_ticker.py`
assumed the flat technicals shape (`adx` is a scalar) but `get_technicals()`
returned the nested shape (`adx` is a dict `{"adx", "dmp", "dmn"}`), so
`adx_value >= 25` raised `TypeError` before the first `await` — Logfire
never saw a span and the brief silently shipped with 0 BUY recs.

This test exercises the real `_flatten_row` → `format_ticker_briefing`
path with a fixture modeled on vnstock's raw output. Any regression that
unflattens or misaligns the keys will raise `TypeError` here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# Raw vnstock shape — nested supertrend/adx/bbands/stoch, matches
# scripts/data/technicals.py::fetch_technicals_async output.
_NESTED_RAW = {
    "TCB": {
        "rsi": 52.3,
        "ma20": 35_500,
        "ma50": 34_000,
        "macd": 0.15,
        "macd_signal": 0.12,
        "macd_histogram": 0.03,
        "atr": 850.0,
        "price_vs_ma20": "above",
        "price_vs_ma50": "above",
        "close": 35_800,
        "supertrend": {"value": 34_200, "direction": "up", "lower": 33_800, "upper": 36_100},
        "adx": {"adx": 27.0, "dmp": 22.5, "dmn": 14.1},
        "bbands": {"lower": 33_800, "middle": 35_500, "upper": 37_200},
        "stoch": {"k": 55.0, "d": 48.0},
        "levels": {"swing_high": 37_000, "swing_low": 33_000},
        "pattern": None,
        "trend": "UPTREND",
        "analysis": "TCB: UPTREND.",
        "closed_at_low": False,
        "volume_vs_avg": 1.2,
    }
}


@pytest.mark.asyncio
async def test_get_technicals_feeds_format_ticker_briefing_without_typeerror():
    """get_technicals must return shape that context_blocks_ticker accepts.

    Before Fix 1 (2026-04-20): get_technicals returned nested shape with
    `adx` as a dict, context_blocks_ticker.py did `adx >= 25` → TypeError.
    After Fix 1: `adx` is a scalar float; comparison succeeds.
    """
    with patch(
        "shared.api.technicals.fetch_technicals_async",
        AsyncMock(return_value=_NESTED_RAW),
    ):
        from pipeline.context_blocks_ticker import format_ticker_briefing
        from shared.api.technicals import get_technicals

        technicals = await get_technicals(["TCB"])

        # Shape check — scalar, not dict
        assert isinstance(technicals["TCB"]["adx"], float)
        assert technicals["TCB"]["supertrend_direction"] == "up"

        # The actual seam: briefing renders without raising TypeError.
        briefing = format_ticker_briefing("TCB", technicals=technicals["TCB"])

    # ADX 27 ≥ 25 → "strong" tag must appear
    assert "ADX: 27 (strong)" in briefing
    # DM+/DM- populated from flat adx_dmp/adx_dmn
    assert "DM+/DM-: 22/14 (bullish)" in briefing


@pytest.mark.asyncio
async def test_format_ticker_briefing_handles_none_adx():
    """Regression guard: tickers with no ADX must not render an ADX line.

    Ensures `adx_value is not None` check still guards the scalar-only branch.
    """
    no_adx_raw = {
        "WEAK": {
            "rsi": 48.0,
            "close": 20_000,
            "supertrend": None,
            "adx": None,
            "bbands": None,
            "stoch": None,
        }
    }
    with patch(
        "shared.api.technicals.fetch_technicals_async",
        AsyncMock(return_value=no_adx_raw),
    ):
        from pipeline.context_blocks_ticker import format_ticker_briefing
        from shared.api.technicals import get_technicals

        technicals = await get_technicals(["WEAK"])
        briefing = format_ticker_briefing("WEAK", technicals=technicals["WEAK"])

    assert "ADX:" not in briefing
    assert "DM+/DM-:" not in briefing


@pytest.mark.asyncio
async def test_briefing_renders_adx_direction_tag_when_strong_and_rising():
    """ADX ≥ 25 + rising series → briefing shows '(strong, rising)' tag."""
    raw = {
        "FPT": {
            "rsi": 60.0,
            "rsi_series": [52.0, 54.0, 57.0, 60.0, 62.0],
            "close": 120_000,
            "supertrend": {"value": 115_000, "direction": "UP", "lower": None, "upper": None},
            "adx": {
                "adx": 32.0,
                "dmp": 25.0,
                "dmn": 14.0,
                "series": [22.0, 25.0, 27.0, 30.0, 32.0],
            },
            "macd": {
                "MACD": 0.5,
                "signal": 0.3,
                "histogram": 0.2,
                "histogram_series": [0.05, 0.1, 0.15, 0.2],
            },
            "macd_histogram": 0.2,
            "bbands": None,
            "stoch": None,
        }
    }
    # Rising volume bars → _calc_volume_context emits volume_trend="increasing".
    rising_volume_bars = {
        "FPT": {
            "data": [
                {
                    "open": 118,
                    "high": 119,
                    "low": 117,
                    "close": 118,
                    "volume": 100_000,
                    "time": "2026-04-19",
                },
                {
                    "open": 118,
                    "high": 120,
                    "low": 117,
                    "close": 119,
                    "volume": 150_000,
                    "time": "2026-04-20",
                },
                {
                    "open": 119,
                    "high": 121,
                    "low": 118,
                    "close": 120,
                    "volume": 200_000,
                    "time": "2026-04-21",
                },
            ]
        }
    }
    with (
        patch("shared.api.technicals.fetch_technicals_async", AsyncMock(return_value=raw)),
        patch(
            "shared.vnstock_client.fetch_history_batch",
            AsyncMock(return_value=rising_volume_bars),
        ),
    ):
        from pipeline.context_blocks_ticker import format_ticker_briefing
        from shared.api.technicals import get_batch_ticker_technicals

        technicals = await get_batch_ticker_technicals(["FPT"])
        briefing = format_ticker_briefing("FPT", technicals=technicals["FPT"])

    assert "ADX: 32 (strong, rising)" in briefing
    assert "RSI: 60.0 (neutral, rising)" in briefing
    assert "MACD hist: +0.20 (positive, rising)" in briefing
    assert "Vol: rising" in briefing


@pytest.mark.asyncio
async def test_briefing_renders_adx_fading_tag():
    """ADX ≥ 25 + falling series → briefing shows '(strong, fading)' tag."""
    raw = {
        "VCB": {
            "rsi": 50.0,
            "rsi_series": [58.0, 56.0, 54.0, 52.0, 50.0],
            "close": 80_000,
            "supertrend": {"value": 78_000, "direction": "UP", "lower": None, "upper": None},
            "adx": {
                "adx": 30.0,
                "dmp": 22.0,
                "dmn": 16.0,
                "series": [38.0, 36.0, 34.0, 32.0, 30.0],
            },
            "macd": {
                "MACD": 0.1,
                "signal": 0.15,
                "histogram": -0.05,
                "histogram_series": [0.1, 0.05, 0.0, -0.05],
            },
            "macd_histogram": -0.05,
            "bbands": None,
            "stoch": None,
        }
    }
    falling_volume_bars = {
        "VCB": {
            "data": [
                {
                    "open": 81,
                    "high": 82,
                    "low": 80,
                    "close": 81,
                    "volume": 300_000,
                    "time": "2026-04-19",
                },
                {
                    "open": 81,
                    "high": 81,
                    "low": 79,
                    "close": 80,
                    "volume": 200_000,
                    "time": "2026-04-20",
                },
                {
                    "open": 80,
                    "high": 80,
                    "low": 79,
                    "close": 80,
                    "volume": 100_000,
                    "time": "2026-04-21",
                },
            ]
        }
    }
    with (
        patch("shared.api.technicals.fetch_technicals_async", AsyncMock(return_value=raw)),
        patch(
            "shared.vnstock_client.fetch_history_batch",
            AsyncMock(return_value=falling_volume_bars),
        ),
    ):
        from pipeline.context_blocks_ticker import format_ticker_briefing
        from shared.api.technicals import get_batch_ticker_technicals

        technicals = await get_batch_ticker_technicals(["VCB"])
        briefing = format_ticker_briefing("VCB", technicals=technicals["VCB"])

    assert "ADX: 30 (strong, fading)" in briefing
    assert "RSI: 50.0 (neutral, falling)" in briefing
    assert "MACD hist: -0.05 (negative, falling)" in briefing
    assert "Vol: falling" in briefing
