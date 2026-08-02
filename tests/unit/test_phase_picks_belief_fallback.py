"""belief_boosted_tickers seam for compute_top_picks + extract_top_picks.

When sector agents partially fail (e.g. 3/5 hang on z-ai/glm-5) but the
deterministic aggregator emits BULLISH beliefs, those tickers must still
reach the picks gate — otherwise a degraded morning ships 0 BUY picks
despite having actionable signal.

The seam runs through a `belief_boosted_tickers: set[str]` kwarg matching
the existing `catalyst_boosted_tickers` pattern.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_belief_boosted_tickers_add_candidates_through_combined_path(
    mock_trading_config,
):
    """1 BUY signal + 3 BULLISH beliefs → screen_buy_signals sees 4 candidates."""
    from pipeline.phase_picks import compute_top_picks

    sector_signal = {"ticker": "VPB", "signal": "BUY", "note": "pullback", "sector": "Banking"}
    beliefs = [
        {"ticker": "VHM", "direction": "BULLISH", "ensemble_type": "sector"},
        {"ticker": "HCM", "direction": "BULLISH", "ensemble_type": "sector"},
        {"ticker": "VRE", "direction": "BULLISH", "ensemble_type": "sector"},
    ]
    belief_boosted = {"VHM", "HCM", "VRE"}

    captured_signals: list[list[dict]] = []

    async def _capture_screen(signals, _cfg):
        captured_signals.append(signals)
        return signals, []

    with (
        patch(
            "pipeline.phase_picks.extract_top_picks",
            AsyncMock(return_value=[]),
        ) as mock_extract,
        patch(
            "pipeline.phase_picks.screen_buy_signals",
            AsyncMock(side_effect=_capture_screen),
        ),
        patch(
            "pipeline.phase_picks.get_position_scale_factor",
            AsyncMock(return_value={"scale_factor": 1.0}),
        ),
        patch("pipeline.phase_picks.validate_sector_signals", return_value=[]),
        patch(
            "pipeline.phase_picks.get_latest_aggregated_beliefs",
            AsyncMock(return_value=[]),
        ),
    ):
        await compute_top_picks(
            sector_signals=[sector_signal],
            scan_date=date(2026, 4, 22),
            technicals={},
            sector_rotation=None,
            holdings_tickers=[],
            deterministic_beliefs=beliefs,
            belief_boosted_tickers=belief_boosted,
        )

    # Screened combined list carried 4 entries: the sector BUY + 3 belief-boosted.
    assert len(captured_signals) == 1
    tickers_screened = {s["ticker"] for s in captured_signals[0]}
    assert tickers_screened == {"VPB", "VHM", "HCM", "VRE"}
    # extract_top_picks received the set verbatim so it can tag `source`.
    kwargs = mock_extract.await_args.kwargs
    assert kwargs["belief_boosted_tickers"] == belief_boosted


@pytest.mark.asyncio
async def test_belief_fallback_source_tag_propagates_to_pick(mock_trading_config):
    """Picks built from belief-boosted tickers carry source='belief_fallback'."""
    from agents.picks import extract_top_picks

    signal = {
        "ticker": "HCM",
        "signal": "BUY",
        "sector": "BELIEF_FALLBACK",
        "note": "BULLISH aggregator belief",
        "source": "belief_fallback",
    }

    # Stub batch ticker data: one valid setup at R:R = 3.0.
    setup = {
        "valid": True,
        "risk_reward": 3.0,
        "entry": 30000,
        "stop": 29000,
        "target": 33000,
        "close": 30000,
        "shares": 100,
        "levels_used": {},
        "exit_family": "FIXED_TARGET",
        "target_basis": "conservative",
    }

    fake_batch = {"HCM": {"trade_setup": setup, "close": 30000, "levels": {}, "atr": 100}}

    with (
        patch("agents.picks.get_batch_ticker_data_async", AsyncMock(return_value=fake_batch)),
        patch(
            "agents.picks.apply_exit_strategy",
            return_value=(True, None, 3.0),
        ),
        patch(
            "agents.picks.classify_strategy",
            return_value=type(
                "_SC",
                (),
                {"strategy": "MEAN_REVERSION", "confidence": 0.9, "matched_signals": []},
            )(),
        ),
        patch(
            "agents.picks.compute_exit_plan",
            return_value={"ladder": []},
        ),
        patch(
            "agents.picks.simulate_trade",
            return_value=type(
                "_Sim",
                (),
                {
                    "expected_return_pct": 5.0,
                    "p_target": 0.5,
                    "p_stop": 0.3,
                    "recommended_action": "TAKE",
                },
            )(),
        ),
    ):
        picks = await extract_top_picks(
            sector_signals=[signal],
            scan_date=date(2026, 4, 22),
            min_rr=2.5,
            max_picks=3,
            scale_factor=1.0,
            exclude_tickers=[],
            beliefs_by_ticker=None,
            risk_regime="CAUTIOUS",
            catalyst_boosted_tickers=None,
            belief_boosted_tickers={"HCM"},
        )

    assert len(picks) == 1
    assert picks[0]["ticker"] == "HCM"
    assert picks[0]["source"] == "belief_fallback"


@pytest.mark.asyncio
async def test_belief_fallback_sector_signal_still_passes_fundamental_gate(
    mock_trading_config,
):
    """Synthetic belief-fallback signal flows through screen_buy_signals unchanged."""
    from pipeline.phase_picks import compute_top_picks

    beliefs = [
        {
            "ticker": "HCM",
            "direction": "BULLISH",
            "ensemble_type": "sector",
            "belief_narrative": "broker rotation",
        }
    ]
    received_signal_shapes: list[dict] = []

    async def _capture_screen(signals, _cfg):
        for s in signals:
            received_signal_shapes.append(dict(s))
        # Reject none — test verifies pass-through, not filter behavior.
        return signals, []

    with (
        patch("pipeline.phase_picks.extract_top_picks", AsyncMock(return_value=[])),
        patch(
            "pipeline.phase_picks.screen_buy_signals",
            AsyncMock(side_effect=_capture_screen),
        ),
        patch(
            "pipeline.phase_picks.get_position_scale_factor",
            AsyncMock(return_value={"scale_factor": 1.0}),
        ),
        patch("pipeline.phase_picks.validate_sector_signals", return_value=[]),
        patch(
            "pipeline.phase_picks.get_latest_aggregated_beliefs",
            AsyncMock(return_value=[]),
        ),
    ):
        await compute_top_picks(
            sector_signals=[],
            scan_date=date(2026, 4, 22),
            technicals={},
            sector_rotation=None,
            holdings_tickers=[],
            deterministic_beliefs=beliefs,
            belief_boosted_tickers={"HCM"},
        )

    # The synthetic signal has all fields screen_buy_signals needs: ticker + signal=BUY.
    assert len(received_signal_shapes) == 1
    assert received_signal_shapes[0]["ticker"] == "HCM"
    assert received_signal_shapes[0]["signal"] == "BUY"
    assert received_signal_shapes[0]["source"] == "belief_fallback"
    # Belief narrative surfaces so synthesis can cite the reason for the promotion.
    assert received_signal_shapes[0]["note"] == "broker rotation"
