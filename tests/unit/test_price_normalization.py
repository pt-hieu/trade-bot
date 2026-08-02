"""Unit tests verifying price normalization pipeline.

Ensures get_prices() returns VND integers and get_financial_ratios()
returns whole-number percentages (rule 18).
"""

from unittest.mock import AsyncMock, patch

import pytest


def _ohlcv_records(closes: list[float]) -> list[dict]:
    """Build OHLCV records from close prices (in thousands VND)."""
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


class TestPriceNormalizationEdgeCases:
    """Verify VND integer output for edge cases."""

    @pytest.mark.asyncio
    async def test_penny_stock_below_1000_vnd(self):
        """SHB-like stock at 0.8 thousands = 800 VND."""
        mock_result = {"PENNY": {"data": _ohlcv_records([0.7, 0.8]), "count": 2}}
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import get_prices

            result = await get_prices(["PENNY"])

        assert result["PENNY"]["close"] == 800
        assert result["PENNY"]["open"] == 792  # 0.8 * 0.99 * 1000

    @pytest.mark.asyncio
    async def test_prices_are_integers(self):
        """All price fields must be int."""
        mock_result = {"FPT": {"data": _ohlcv_records([79.5, 80.2]), "count": 2}}
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import get_prices

            result = await get_prices(["FPT"])

        for field in ("open", "high", "low", "close"):
            assert isinstance(result["FPT"][field], int), f"{field} should be int"

    @pytest.mark.asyncio
    async def test_change_pct_is_whole_number(self):
        """change_pct should be whole number % (e.g., 2.15 not 0.0215)."""
        mock_result = {"TCB": {"data": _ohlcv_records([35.0, 35.7]), "count": 2}}
        with patch("shared.api.prices.fetch_history_batch", AsyncMock(return_value=mock_result)):
            from shared.api.prices import get_prices

            result = await get_prices(["TCB"])

        assert result["TCB"]["change_pct"] == pytest.approx(2.0, rel=0.01)


class TestFundamentalsNormalization:
    """Verify financial ratios return whole-number percentages."""

    @pytest.mark.asyncio
    async def test_roe_is_whole_pct(self):
        """ROE 0.2827 from API should become 28.27."""
        mock_ratios = {
            "data": [
                {
                    "period": "2024-Q4",
                    "ROE (%)": 0.2827,
                    "ROA (%)": 0.08,
                    "After-tax Profit Margin (%)": 0.1601,
                    "Gross Margin (%)": 0.3693,
                    "EBIT Margin (%)": 0.22,
                    "P/E": 14.4,
                    "P/B": 3.7,
                    "EPS basic (VND)": 5500,
                    "Debt to Equity": 1.0,
                    "Current Ratio": 1.5,
                }
            ]
        }
        with patch("shared.api.fundamentals._fetch_ratios", AsyncMock(return_value=mock_ratios)):
            from shared.api.fundamentals import get_financial_ratios

            result = await get_financial_ratios("FPT")

        assert len(result) == 1
        r = result[0]
        assert r["roe"] == pytest.approx(28.27)
        assert r["net_margin"] == pytest.approx(16.01)
        assert r["gross_margin"] == pytest.approx(36.93)
        assert r["roa"] == pytest.approx(8.0)
        assert r["operating_margin"] == pytest.approx(22.0)
        # Ratios stay as-is
        assert r["pe"] == pytest.approx(14.4)
        assert r["pb"] == pytest.approx(3.7)

    @pytest.mark.asyncio
    async def test_small_roe_half_percent(self):
        """ROE of 0.005 (0.5%) should not be misclassified."""
        mock_ratios = {
            "data": [
                {
                    "period": "2024-Q4",
                    "ROE (%)": 0.005,
                    "ROA (%)": 0.002,
                    "After-tax Profit Margin (%)": 0.01,
                    "Gross Margin (%)": 0.05,
                    "EBIT Margin (%)": 0.02,
                    "P/E": 50.0,
                    "P/B": 1.0,
                    "EPS basic (VND)": 100,
                    "Debt to Equity": 3.0,
                    "Current Ratio": 0.8,
                }
            ]
        }
        with patch("shared.api.fundamentals._fetch_ratios", AsyncMock(return_value=mock_ratios)):
            from shared.api.fundamentals import get_financial_ratios

            result = await get_financial_ratios("WEAK")

        r = result[0]
        assert r["roe"] == pytest.approx(0.5)  # 0.5%, not 50%
        assert r["net_margin"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_negative_margin(self):
        """Negative net margin (-5.2%) should normalize correctly."""
        mock_ratios = {
            "data": [
                {
                    "period": "2024-Q4",
                    "ROE (%)": -0.08,
                    "ROA (%)": -0.03,
                    "After-tax Profit Margin (%)": -0.052,
                    "Gross Margin (%)": 0.10,
                    "EBIT Margin (%)": -0.04,
                    "P/E": None,
                    "P/B": 0.8,
                    "EPS basic (VND)": -500,
                    "Debt to Equity": 2.0,
                    "Current Ratio": 0.6,
                }
            ]
        }
        with patch("shared.api.fundamentals._fetch_ratios", AsyncMock(return_value=mock_ratios)):
            from shared.api.fundamentals import get_financial_ratios

            result = await get_financial_ratios("LOSS")

        r = result[0]
        assert r["roe"] == pytest.approx(-8.0)
        assert r["net_margin"] == pytest.approx(-5.2)
        assert r["operating_margin"] == pytest.approx(-4.0)
