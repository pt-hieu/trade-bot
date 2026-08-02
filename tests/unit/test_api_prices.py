"""Unit tests for shared/api/prices.py."""

from unittest.mock import AsyncMock, patch

import pytest


def _ohlcv_records(closes: list[float]) -> list[dict]:
    """Build OHLCV records from close prices, dated 2026-02-01 onwards."""
    return [
        {
            "time": f"2026-02-{i + 1:02d}",
            "open": c * 0.99,
            "high": c * 1.02,
            "low": c * 0.97,
            "close": c,
            "volume": 1_000_000,
        }
        for i, c in enumerate(closes)
    ]


def _batch_result(**symbol_closes: list[float]) -> dict:
    """Build fetch_history_batch return dict from keyword args: symbol → closes."""
    return {
        sym.upper(): {"data": _ohlcv_records(closes), "count": len(closes)}
        for sym, closes in symbol_closes.items()
    }


# ── get_prices ────────────────────────────────────────────────────────────────


class TestGetPrices:
    @pytest.mark.asyncio
    async def test_returns_ohlcv_dict(self):
        # Arrange
        mock_result = _batch_result(TCB=[34.0, 35.0, 35.5])

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import get_prices

            result = await get_prices(["TCB"])

        # Assert
        assert "TCB" in result
        assert result["TCB"]["close"] == 35500
        for field in ("date", "open", "high", "low", "volume", "change_pct"):
            assert field in result["TCB"], f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_computes_change_pct_positive(self):
        # Arrange
        mock_result = _batch_result(FPT=[100.0, 102.0])

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import get_prices

            result = await get_prices(["FPT"])

        # Assert
        assert result["FPT"]["change_pct"] == pytest.approx(2.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_computes_change_pct_negative(self):
        # Arrange
        mock_result = _batch_result(VHM=[120.0, 114.0])

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import get_prices

            result = await get_prices(["VHM"])

        # Assert
        assert result["VHM"]["change_pct"] == pytest.approx(-5.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty(self):
        # Act / Assert (no API call needed)
        from shared.api.prices import get_prices

        result = await get_prices([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_skips_error_tickers(self):
        # Arrange
        mock_result = {
            "TCB": {"data": _ohlcv_records([34.0, 35.0]), "count": 2},
            "BAD": {"error": "not found"},
        }

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import get_prices

            result = await get_prices(["TCB", "BAD"])

        # Assert
        assert "TCB" in result
        assert "BAD" not in result

    @pytest.mark.asyncio
    async def test_single_record_change_pct_is_none(self):
        # Arrange
        mock_result = _batch_result(TCB=[35.0])

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import get_prices

            result = await get_prices(["TCB"])

        # Assert
        assert result["TCB"]["change_pct"] is None

    @pytest.mark.asyncio
    async def test_uppercases_tickers(self):
        # Arrange
        mock_result = {"TCB": {"data": _ohlcv_records([35.0, 35.5]), "count": 2}}

        # Act
        with patch(
            "shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)
        ) as m:
            from shared.api.prices import get_prices

            await get_prices(["tcb"])

        # Assert: symbols arg is uppercased
        symbols_called = m.call_args.kwargs.get("symbols", [])
        assert "TCB" in symbols_called


# ── compute_daily_return ──────────────────────────────────────────────────────


class TestComputeDailyReturn:
    @pytest.mark.asyncio
    async def test_positive_return(self):
        # Arrange
        mock_result = _batch_result(VNINDEX=[1200.0, 1212.0])

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import compute_daily_return

            result = await compute_daily_return()

        # Assert
        assert result == pytest.approx(1.0, rel=0.001)

    @pytest.mark.asyncio
    async def test_negative_return(self):
        # Arrange
        mock_result = _batch_result(VNINDEX=[1200.0, 1188.0])

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import compute_daily_return

            result = await compute_daily_return()

        # Assert
        assert result == pytest.approx(-1.0, rel=0.001)

    @pytest.mark.asyncio
    async def test_zero_return_flat_market(self):
        # Arrange
        mock_result = _batch_result(VNINDEX=[1200.0, 1200.0])

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import compute_daily_return

            result = await compute_daily_return()

        # Assert
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_insufficient_data_returns_none(self):
        # Arrange
        mock_result = _batch_result(VNINDEX=[1200.0])

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import compute_daily_return

            result = await compute_daily_return()

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_custom_ticker(self):
        # Arrange
        mock_result = {"TCB": {"data": _ohlcv_records([35.0, 35.7]), "count": 2}}

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import compute_daily_return

            result = await compute_daily_return(ticker="TCB")

        # Assert
        assert result == pytest.approx(2.0, rel=0.01)


# ── compute_relative_strength ─────────────────────────────────────────────────


class TestComputeRelativeStrength:
    def _rs_batch(self, vnindex_closes: list[float], ticker_closes: dict[str, list[float]]) -> dict:
        result = {"VNINDEX": {"data": _ohlcv_records(vnindex_closes), "count": len(vnindex_closes)}}
        for sym, closes in ticker_closes.items():
            result[sym.upper()] = {"data": _ohlcv_records(closes), "count": len(closes)}
        return result

    @pytest.mark.asyncio
    async def test_rs_above_1_when_ticker_outperforms(self):
        # Arrange: TCB +10%, VNINDEX flat over 20 days
        vnindex = [1200.0] * 22  # 22 bars → window=20 + 1 lag + current
        tcb = [35.0] + [35.0] * 20 + [38.5]  # +10% over 20 bars

        mock_result = self._rs_batch(vnindex, {"TCB": tcb})

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import compute_relative_strength

            result = await compute_relative_strength(["TCB"])

        # Assert
        assert result["TCB"] is not None
        assert result["TCB"] > 1.0

    @pytest.mark.asyncio
    async def test_rs_below_1_when_ticker_underperforms(self):
        # Arrange: VNINDEX +5%, TCB flat
        vnindex = [1200.0] + [1200.0] * 20 + [1260.0]  # +5%
        tcb = [35.0] * 22  # flat

        mock_result = self._rs_batch(vnindex, {"TCB": tcb})

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import compute_relative_strength

            result = await compute_relative_strength(["TCB"])

        # Assert
        assert result["TCB"] is not None
        assert result["TCB"] < 1.0

    @pytest.mark.asyncio
    async def test_rs_approx_1_when_matches_vnindex(self):
        # Arrange: both rise exactly 5% over 20 days
        vnindex = [1200.0] + [1200.0] * 20 + [1260.0]  # +5%
        tcb = [35.0] + [35.0] * 20 + [36.75]  # +5%

        mock_result = self._rs_batch(vnindex, {"TCB": tcb})

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import compute_relative_strength

            result = await compute_relative_strength(["TCB"])

        # Assert
        assert result["TCB"] == pytest.approx(1.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_insufficient_data_returns_none_per_ticker(self):
        # Arrange: only 5 records — not enough for window=20+1
        mock_result = self._rs_batch([1200.0] * 5, {"TCB": [35.0] * 5})

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import compute_relative_strength

            result = await compute_relative_strength(["TCB"])

        # Assert
        assert result["TCB"] is None

    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty_dict(self):
        # Act / Assert: no API call for empty list
        from shared.api.prices import compute_relative_strength

        result = await compute_relative_strength([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_multiple_tickers(self):
        # Arrange
        vnindex = [1200.0] * 22
        mock_result = self._rs_batch(vnindex, {"TCB": [35.0] * 22, "FPT": [100.0] * 22})

        # Act
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import compute_relative_strength

            result = await compute_relative_strength(["TCB", "FPT"])

        # Assert: both tickers present in result
        assert "TCB" in result
        assert "FPT" in result
