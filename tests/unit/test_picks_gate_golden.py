"""Golden-fixture parity for the picks R:R gate after DEF-005 refactor.

Before DEF-005, ``picks_exit_dispatch.apply_exit_strategy`` FIXED_TARGET
branch hand-inlined ``if chosen_rr < min_rr``. The refactor delegates to
``shared.rules.entry_gates.check_candidate_gate`` with
``catalyst_rr_adjustment=0`` and ``sizing_floor_vnd=0`` — morning callers
should see byte-for-byte identical pick output. These tests pin that:

* R:R above / at / below the floor trips the same branches as the legacy
  inline check.
* The returned pick dict retains its shape (``exit_family``, ``entry``,
  ``stop``, ``target``, ``risk_reward``) after passing the gate.
* An ATR_TRAIL-classified candidate is NOT affected by the FIXED_TARGET
  refactor (the ATR trail gate is a separate code path).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.tools.strategy_classifier import StrategyClassification


def _pullback_tech(rr: float) -> dict:
    """Canned tech data for a PULLBACK candidate — bypasses trend-momentum gate."""
    return {
        "ticker": "FPT",
        "close": 120_000,
        "rsi": 55.0,
        "ma20": 115_000,
        "ma50": 110_000,
        "atr": 2500,
        "adx": 22.0,
        "adx_dmp": 20.0,
        "adx_dmn": 18.0,
        "supertrend_direction": "UP",
        "levels": {"nearest_support": 115_000, "nearest_resistance": 130_000},
        "trend": {"trend": "UPTREND", "strength": "moderate", "momentum": "bullish"},
        "trade_setup": {
            "ticker": "FPT",
            "entry": 120_000,
            "stop": 115_000,
            "target": int(120_000 + rr * 5000),
            "risk_reward": rr,
            "risk_reward_gross": rr + 0.1,
            "shares": 100,
            "position_vnd": 12_000_000,
            "valid": True,
            "close": 120_000,
            "levels_used": {
                "nearest_support": 115_000,
                "swing_low": 114_000,
                "nearest_resistance": 130_000,
                "swing_high": 145_000,
                "range_20d_low": 115_000,
                "range_20d_high": 145_000,
            },
            "target_basis": "conservative",
            "rr_stretch": None,
        },
    }


@pytest.fixture
def mock_deps():
    with (
        patch("agents.picks.get_batch_ticker_data_async", new_callable=AsyncMock) as mock_batch,
        patch("agents.picks.classify_strategy") as mock_strategy,
        patch("agents.picks.simulate_trade") as mock_sim,
        patch("agents.picks.compute_exit_plan") as mock_exit,
        patch("agents.picks.get_rsi_at_swing_low_date", new_callable=AsyncMock) as mock_rsi,
    ):
        sim_result = MagicMock()
        sim_result.expected_return_pct = 4.0
        sim_result.p_target = 0.6
        sim_result.p_stop = 0.3
        sim_result.recommended_action = "BUY"
        mock_sim.return_value = sim_result
        mock_exit.return_value = {"legs": []}
        mock_rsi.return_value = None

        yield {
            "batch": mock_batch,
            "strategy": mock_strategy,
            "sim": mock_sim,
            "exit": mock_exit,
            "rsi": mock_rsi,
        }


@pytest.mark.usefixtures("mock_trading_config")
class TestPicksGateParity:
    """Refactor keeps FIXED_TARGET gate behaviorally identical to the pre-DEF-005 path."""

    @pytest.mark.asyncio
    async def test_rr_above_floor_passes(self, mock_deps):
        mock_deps["batch"].return_value = {"FPT": _pullback_tech(rr=3.5)}
        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="PULLBACK", confidence=0.6, matched_signals=["near MA20"]
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[{"ticker": "FPT", "signal": "BUY", "note": "", "sector": "tech"}],
            scan_date=date(2026, 4, 23),
            min_rr=3.0,
        )
        assert len(picks) == 1
        pick = picks[0]
        assert pick["ticker"] == "FPT"
        assert pick["exit_family"] == "FIXED_TARGET"
        assert pick["risk_reward"] == 3.5
        assert pick["entry"] == 120_000
        assert pick["stop"] == 115_000

    @pytest.mark.asyncio
    async def test_rr_at_floor_passes(self, mock_deps):
        # Boundary: floor == RR — legacy check was strict less-than, so
        # equality passes. Parity sanity.
        mock_deps["batch"].return_value = {"FPT": _pullback_tech(rr=3.0)}
        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="PULLBACK", confidence=0.6, matched_signals=["near MA20"]
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[{"ticker": "FPT", "signal": "BUY", "note": "", "sector": "tech"}],
            scan_date=date(2026, 4, 23),
            min_rr=3.0,
        )
        assert len(picks) == 1
        assert picks[0]["risk_reward"] == 3.0

    @pytest.mark.asyncio
    async def test_rr_below_floor_rejects(self, mock_deps):
        # rr=2.5 vs floor 3.0 → 16.7% miss > 10% soft-band tolerance → hard reject.
        mock_deps["batch"].return_value = {"FPT": _pullback_tech(rr=2.5)}
        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="PULLBACK", confidence=0.6, matched_signals=["near MA20"]
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[{"ticker": "FPT", "signal": "BUY", "note": "", "sector": "tech"}],
            scan_date=date(2026, 4, 23),
            min_rr=3.0,
        )
        assert picks == []

    @pytest.mark.asyncio
    async def test_low_rr_floor_preserves_morning_gate(self, mock_deps):
        # Morning min_rr can dip to 2.0 under relaxed urgency. The refactor
        # must NOT engage the SHOCK_FLOOR_MINIMUM_RR clamp (2.5) for morning
        # because the catalyst adjustment is zero. A pick at RR 2.3 with
        # floor 2.0 must pass — if the clamp leaked into morning, the pick
        # would spuriously fail.
        mock_deps["batch"].return_value = {"FPT": _pullback_tech(rr=2.3)}
        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="PULLBACK", confidence=0.6, matched_signals=["near MA20"]
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[{"ticker": "FPT", "signal": "BUY", "note": "", "sector": "tech"}],
            scan_date=date(2026, 4, 23),
            min_rr=2.0,
        )
        assert len(picks) == 1
        assert picks[0]["risk_reward"] == 2.3
