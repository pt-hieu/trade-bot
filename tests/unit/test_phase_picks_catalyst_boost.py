"""compute_top_picks must forward catalyst_boosted_tickers into extract_top_picks.

Without the kwarg threading, the strategy classifier's MR→MOMENTUM promotion
is dead code and ATR_TRAIL exit dispatch never fires for catalyst-active tickers.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_catalyst_boosted_tickers_forwarded_to_extract_top_picks(mock_trading_config):
    """compute_top_picks must pass catalyst_boosted_tickers kwarg through."""
    from pipeline.phase_picks import compute_top_picks

    sample_signal = {"ticker": "VHM", "signal": "BUY", "note": "rally", "sector": "Real Estate"}
    boost_set = {"VHM", "VIC"}

    with (
        patch(
            "pipeline.phase_picks.extract_top_picks",
            AsyncMock(return_value=[]),
        ) as mock_extract,
        patch(
            "pipeline.phase_picks.screen_buy_signals",
            AsyncMock(return_value=([sample_signal], [])),
        ),
        patch(
            "pipeline.phase_picks.get_position_scale_factor",
            AsyncMock(return_value={"scale_factor": 1.0}),
        ),
        patch(
            "pipeline.phase_picks.validate_sector_signals",
            return_value=[],
        ),
        patch(
            "pipeline.phase_picks.get_latest_aggregated_beliefs",
            AsyncMock(return_value=[]),
        ),
    ):
        await compute_top_picks(
            sector_signals=[sample_signal],
            scan_date=date(2026, 4, 19),
            technicals={"VHM": {"trade_setup": {"valid": True, "risk_reward": 3.0}}},
            sector_rotation=None,
            holdings_tickers=[],
            catalyst_boosted_tickers=boost_set,
        )

    assert mock_extract.await_count == 1
    kwargs = mock_extract.await_args.kwargs
    assert kwargs["catalyst_boosted_tickers"] == boost_set, (
        "catalyst_boosted_tickers must forward into extract_top_picks — without "
        "this kwarg the MR→MOMENTUM promotion never fires."
    )


@pytest.mark.asyncio
async def test_compute_top_picks_passes_none_when_no_boost_given(mock_trading_config):
    """When caller omits the kwarg, extract_top_picks receives None explicitly."""
    from pipeline.phase_picks import compute_top_picks

    with (
        patch(
            "pipeline.phase_picks.extract_top_picks",
            AsyncMock(return_value=[]),
        ) as mock_extract,
        patch(
            "pipeline.phase_picks.screen_buy_signals",
            AsyncMock(return_value=([], [])),
        ),
        patch(
            "pipeline.phase_picks.get_position_scale_factor",
            AsyncMock(return_value={"scale_factor": 1.0}),
        ),
        patch(
            "pipeline.phase_picks.validate_sector_signals",
            return_value=[],
        ),
        patch(
            "pipeline.phase_picks.get_latest_aggregated_beliefs",
            AsyncMock(return_value=[]),
        ),
    ):
        await compute_top_picks(
            sector_signals=[{"ticker": "VHM", "signal": "BUY"}],
            scan_date=date(2026, 4, 19),
            technicals={},
            sector_rotation=None,
            holdings_tickers=[],
        )

    kwargs = mock_extract.await_args.kwargs
    assert kwargs["catalyst_boosted_tickers"] is None
