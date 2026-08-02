"""SWI-354 / SWI-356 / SWI-357: batch-technicals retry + per-ticker fallback."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.tools.technicals import fetch_async


def _ok_row(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "close": 50000,
        "levels": {},
        "atr": 1000,
    }


@pytest.fixture(autouse=True)
def _stub_rs():
    """Stub relative_strength to avoid DB access during these unit tests."""
    with patch(
        "shared.neon.enrichment.get_relative_strength",
        new=AsyncMock(return_value={}),
    ):
        yield


@pytest.mark.asyncio
async def test_batch_fetch_happy_path():
    """No exception → no fallback, real batch result returned."""
    with patch(
        "shared.api.technicals.get_batch_ticker_technicals",
        new=AsyncMock(return_value={"FPT": _ok_row("FPT"), "VPB": _ok_row("VPB")}),
    ):
        result = await fetch_async.get_batch_ticker_data_async(
            ["FPT", "VPB"], scan_date=date(2026, 5, 13)
        )
    assert "error" not in result["FPT"]
    assert "error" not in result["VPB"]


@pytest.mark.asyncio
async def test_batch_fetch_falls_back_to_per_ticker():
    """Batch raises; 2/3 per-ticker calls succeed → 2 real rows, 1 error row."""

    async def _per_ticker(ticker: str):
        if ticker == "BSR":
            raise RuntimeError("per-ticker miss")
        return _ok_row(ticker)

    with (
        patch(
            "shared.api.technicals.get_batch_ticker_technicals",
            new=AsyncMock(side_effect=RuntimeError("batch retries exhausted")),
        ),
        patch(
            "shared.api.technicals.get_ticker_technicals",
            new=AsyncMock(side_effect=_per_ticker),
        ),
    ):
        result = await fetch_async.get_batch_ticker_data_async(
            ["FPT", "VPB", "BSR"], scan_date=date(2026, 5, 13)
        )

    assert "error" not in result["FPT"]
    assert "error" not in result["VPB"]
    assert "error" in result["BSR"]


@pytest.mark.asyncio
async def test_batch_fetch_full_failure_returns_per_ticker_errors():
    """Both batch AND every per-ticker call raise → all rows carry error key."""
    with (
        patch(
            "shared.api.technicals.get_batch_ticker_technicals",
            new=AsyncMock(side_effect=RuntimeError("upstream down")),
        ),
        patch(
            "shared.api.technicals.get_ticker_technicals",
            new=AsyncMock(side_effect=RuntimeError("per-ticker also down")),
        ),
    ):
        result = await fetch_async.get_batch_ticker_data_async(
            ["FPT", "VPB"], scan_date=date(2026, 5, 13)
        )

    assert "error" in result["FPT"]
    assert "error" in result["VPB"]


@pytest.mark.asyncio
async def test_batch_fetch_skips_fallback_above_fanout_cap():
    """21 tickers, batch raises → no per-ticker calls fire (fanout cap)."""
    tickers = [f"T{i:02d}" for i in range(21)]
    per_ticker_mock = AsyncMock(side_effect=AssertionError("must not be called"))

    with (
        patch(
            "shared.api.technicals.get_batch_ticker_technicals",
            new=AsyncMock(side_effect=RuntimeError("batch down")),
        ),
        patch("shared.api.technicals.get_ticker_technicals", new=per_ticker_mock),
    ):
        result = await fetch_async.get_batch_ticker_data_async(tickers, scan_date=date(2026, 5, 13))

    assert all("error" in row for row in result.values())
    per_ticker_mock.assert_not_awaited()
