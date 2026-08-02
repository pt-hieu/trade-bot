"""Unit tests for shared/api/technicals.py."""

from unittest.mock import AsyncMock, patch

import pytest

_SAMPLE_RESULT = {
    "TCB": {
        "rsi": 42.5,
        "ma20": 35.5,
        "ma50": 34.0,
        "macd": 0.15,
        "macd_signal": 0.12,
        "macd_histogram": 0.03,
        "price_vs_ma20": "above",
        "price_vs_ma50": "above",
        "atr": 0.85,
        "supertrend": {"value": 34.2, "direction": "up", "lower": 33.8, "upper": 36.1},
        "adx": {"adx": 22.0, "dmp": 18.5, "dmn": 12.1},
        "bbands": {
            "lower": 33.8,
            "middle": 35.5,
            "upper": 37.2,
            "bandwidth": 0.094,
            "percent": 0.65,
        },
        "stoch": {"k": 55.0, "d": 48.0},
        "levels": {
            "swing_high": 37.0,
            "swing_low": 33.0,
            "range_20d_high": 37.5,
            "range_20d_low": 33.5,
        },
        "pattern": {"pattern": None, "signal": None},
        "trend": {"trend": "UPTREND", "strength": "moderate", "momentum": "bullish"},
        "analysis": "TCB: UPTREND (moderate). RSI 43",
        "closed_at_low": False,
        "volume_vs_avg": 1.2,
    }
}

# `get_technicals()` returns the canonical flat shape (see shared/api/technicals.py::_flatten_row).
# Nested `supertrend`/`adx`/`bbands`/`stoch` dicts are replaced by flat scalars:
# `supertrend_direction`, `adx`, `adx_dmp`, `adx_dmn`. bbands/stoch are dropped.
_EXPECTED_FIELDS = [
    "rsi",
    "ma20",
    "ma50",
    "macd",
    "macd_signal",
    "macd_histogram",
    "price_vs_ma20",
    "price_vs_ma50",
    "atr",
    "supertrend_direction",
    "adx",
    "adx_dmp",
    "adx_dmn",
    "levels",
    "pattern",
    "trend",
    "analysis",
    "closed_at_low",
    "volume_vs_avg",
]


class TestGetTechnicals:
    @pytest.mark.asyncio
    async def test_returns_same_shape_as_old_get_all_technicals(self):
        # Arrange / Act
        with patch(
            "shared.api.technicals.fetch_technicals_async",
            AsyncMock(return_value=_SAMPLE_RESULT),
        ):
            from shared.api.technicals import get_technicals

            result = await get_technicals(["TCB"])

        # Assert — all expected fields present
        assert "TCB" in result
        for field in _EXPECTED_FIELDS:
            assert field in result["TCB"], f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_converts_flat_list_to_watchlist_format(self):
        # Arrange / Act
        with patch(
            "shared.api.technicals.fetch_technicals_async",
            AsyncMock(return_value=_SAMPLE_RESULT),
        ) as mock:
            from shared.api.technicals import get_technicals

            await get_technicals(["TCB", "FPT"])

        # Assert: underlying function receives {"all": ["TCB", "FPT"]}
        call_arg = mock.call_args[0][0]
        assert "all" in call_arg
        assert "TCB" in call_arg["all"]
        assert "FPT" in call_arg["all"]

    @pytest.mark.asyncio
    async def test_uppercases_tickers(self):
        # Arrange / Act
        with patch(
            "shared.api.technicals.fetch_technicals_async",
            AsyncMock(return_value={}),
        ) as mock:
            from shared.api.technicals import get_technicals

            await get_technicals(["tcb", "fpt"])

        # Assert: lowercase input → uppercase in watchlist
        call_arg = mock.call_args[0][0]
        assert "TCB" in call_arg["all"]
        assert "FPT" in call_arg["all"]
        assert "tcb" not in call_arg["all"]

    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty_dict_without_api_call(self):
        # Act
        with patch(
            "shared.api.technicals.fetch_technicals_async",
            AsyncMock(return_value={}),
        ) as mock:
            from shared.api.technicals import get_technicals

            result = await get_technicals([])

        # Assert: no API call, empty result
        assert result == {}
        mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_propagates_error_dict_from_api(self):
        # Arrange
        error_result = {"TCB": {"error": "API timeout"}}

        # Act
        with patch(
            "shared.api.technicals.fetch_technicals_async",
            AsyncMock(return_value=error_result),
        ):
            from shared.api.technicals import get_technicals

            result = await get_technicals(["TCB"])

        # Assert: error dict passed through unchanged
        assert result["TCB"]["error"] == "API timeout"

    @pytest.mark.asyncio
    async def test_returns_flat_canonical_shape(self):
        """Regression: `get_technicals` must return flat `adx`/`supertrend_direction`
        scalars. Pipeline `context_blocks_ticker.py` does `adx_value >= 25` which
        raises TypeError on the old nested shape (c521ebb7 incident 2026-04-20).
        """
        with patch(
            "shared.api.technicals.fetch_technicals_async",
            AsyncMock(return_value=_SAMPLE_RESULT),
        ):
            from shared.api.technicals import get_technicals

            result = await get_technicals(["TCB"])

        tcb = result["TCB"]
        # adx scalar, not dict
        assert tcb["adx"] == 22.0
        assert not isinstance(tcb["adx"], dict)
        assert tcb["adx_dmp"] == 18.5
        assert tcb["adx_dmn"] == 12.1
        # supertrend flattened to direction scalar
        assert tcb["supertrend_direction"] == "up"
        assert "supertrend" not in tcb
        # bbands/stoch dropped
        assert "bbands" not in tcb
        assert "stoch" not in tcb
        # Contract test: `adx >= 25` must not raise
        assert not (tcb["adx"] >= 25)

    @pytest.mark.asyncio
    async def test_returns_computed_fields(self):
        # Arrange / Act
        with patch(
            "shared.api.technicals.fetch_technicals_async",
            AsyncMock(return_value=_SAMPLE_RESULT),
        ):
            from shared.api.technicals import get_technicals

            result = await get_technicals(["TCB"])

        # Assert computed fields present with correct types
        tcb = result["TCB"]
        assert isinstance(tcb["closed_at_low"], bool)
        assert isinstance(tcb["trend"], dict)
        assert isinstance(tcb["pattern"], dict)
        assert "trend" in tcb["trend"]
        assert "pattern" in tcb["pattern"]


# ─── Sample data for get_ticker_technicals ────────────────────────────────────

_SAMPLE_PRICE_MAP = {
    "TCB": {
        "data": [
            {
                "time": "2026-02-24",
                "open": 35.0,
                "high": 36.0,
                "low": 34.5,
                "close": 34.8,
                "volume": 1_200_000,
            },
            {
                "time": "2026-02-25",
                "open": 34.8,
                "high": 35.5,
                "low": 34.2,
                "close": 35.2,
                "volume": 900_000,
            },
            {
                "time": "2026-02-26",
                "open": 35.2,
                "high": 36.1,
                "low": 34.9,
                "close": 35.8,
                "volume": 1_500_000,
            },
        ]
    }
}


class TestGetTickerTechnicals:
    @pytest.mark.asyncio
    async def test_returns_ohlcv_fields(self):
        with (
            patch(
                "shared.api.technicals.fetch_technicals_async",
                AsyncMock(return_value=_SAMPLE_RESULT),
            ),
            patch(
                "shared.vnstock_client.fetch_history_batch",
                AsyncMock(return_value=_SAMPLE_PRICE_MAP),
            ),
        ):
            from shared.api.technicals import get_ticker_technicals

            result = await get_ticker_technicals("TCB")

        for field in ("close", "open", "high", "low", "volume"):
            assert field in result, f"Missing OHLCV field: {field}"

    @pytest.mark.asyncio
    async def test_prices_in_vnd_units(self):
        with (
            patch(
                "shared.api.technicals.fetch_technicals_async",
                AsyncMock(return_value=_SAMPLE_RESULT),
            ),
            patch(
                "shared.vnstock_client.fetch_history_batch",
                AsyncMock(return_value=_SAMPLE_PRICE_MAP),
            ),
        ):
            from shared.api.technicals import get_ticker_technicals

            result = await get_ticker_technicals("TCB")

        # API close 35.8 (thousands VND) → 35_800 VND
        assert result["close"] == 35_800
        assert result["open"] == 35_200
        assert result["high"] == 36_100
        assert result["low"] == 34_900

    @pytest.mark.asyncio
    async def test_returns_flattened_supertrend_direction(self):
        with (
            patch(
                "shared.api.technicals.fetch_technicals_async",
                AsyncMock(return_value=_SAMPLE_RESULT),
            ),
            patch(
                "shared.vnstock_client.fetch_history_batch",
                AsyncMock(return_value=_SAMPLE_PRICE_MAP),
            ),
        ):
            from shared.api.technicals import get_ticker_technicals

            result = await get_ticker_technicals("TCB")

        assert "supertrend_direction" in result
        assert result["supertrend_direction"] == "up"
        assert "supertrend" not in result  # nested dict removed

    @pytest.mark.asyncio
    async def test_returns_flattened_adx_strength_and_dmp_dmn(self):
        with (
            patch(
                "shared.api.technicals.fetch_technicals_async",
                AsyncMock(return_value=_SAMPLE_RESULT),
            ),
            patch(
                "shared.vnstock_client.fetch_history_batch",
                AsyncMock(return_value=_SAMPLE_PRICE_MAP),
            ),
        ):
            from shared.api.technicals import get_ticker_technicals

            result = await get_ticker_technicals("TCB")

        # Raw ADX strength survives flattening — used by context_blocks_ticker
        # adx_rising detection and sector trend-follow BUY criteria.
        assert result["adx"] == 22.0
        assert result["adx_dmp"] == 18.5
        assert result["adx_dmn"] == 12.1
        # No nested dict left behind
        assert not isinstance(result["adx"], dict)

    @pytest.mark.asyncio
    async def test_returns_volume_context(self):
        with (
            patch(
                "shared.api.technicals.fetch_technicals_async",
                AsyncMock(return_value=_SAMPLE_RESULT),
            ),
            patch(
                "shared.vnstock_client.fetch_history_batch",
                AsyncMock(return_value=_SAMPLE_PRICE_MAP),
            ),
        ):
            from shared.api.technicals import get_ticker_technicals

            result = await get_ticker_technicals("TCB")

        vc = result.get("volume_context")
        assert vc is not None
        assert "volume_trend" in vc
        assert "bounce_confirmed" in vc
        assert "prior_down_volume" in vc

    @pytest.mark.asyncio
    async def test_returns_error_dict_on_api_failure(self):
        with (
            patch("shared.api.technicals.fetch_technicals_async", AsyncMock(return_value={})),
            patch("shared.vnstock_client.fetch_history_batch", AsyncMock(return_value={})),
        ):
            from shared.api.technicals import get_ticker_technicals

            result = await get_ticker_technicals("UNKNOWN")

        assert "error" in result
        assert result.get("ticker") == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_uppercases_ticker(self):
        with (
            patch(
                "shared.api.technicals.fetch_technicals_async",
                AsyncMock(return_value={"TCB": _SAMPLE_RESULT["TCB"]}),
            ),
            patch(
                "shared.vnstock_client.fetch_history_batch",
                AsyncMock(return_value=_SAMPLE_PRICE_MAP),
            ),
        ):
            from shared.api.technicals import get_ticker_technicals

            result = await get_ticker_technicals("tcb")

        assert result.get("ticker") == "TCB"
