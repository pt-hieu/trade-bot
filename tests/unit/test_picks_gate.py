"""Tests for deterministic trend-momentum gate in agents.picks.extract_top_picks.

Verifies that TREND/MOMENTUM strategy candidates with fading ADX are dropped,
while rising/flat ADX pass, and non-trend-follow strategies (PULLBACK et al.)
bypass the gate entirely.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.tools.strategy_classifier import StrategyClassification


def _buy_signal(ticker="FPT"):
    return {"ticker": ticker, "signal": "BUY", "note": "Strong setup", "sector": "tech"}


def _trend_follow_tech(
    *,
    adx: float = 32.0,
    adx_dmp: float = 25.0,
    adx_dmn: float = 15.0,
    supertrend_direction: str = "UP",
    adx_rising: bool | None = True,
) -> dict:
    """Tech data shaped for a trend-follow candidate with controllable ADX direction."""
    from shared.rules.trend_momentum import MomentumSignals

    return {
        "ticker": "FPT",
        "close": 120_000,
        "rsi": 62.0,
        "ma20": 115_000,
        "ma50": 110_000,
        "atr": 2500,
        "adx": adx,
        "adx_dmp": adx_dmp,
        "adx_dmn": adx_dmn,
        "supertrend_direction": supertrend_direction,
        "momentum_signals": MomentumSignals(
            adx_rising=adx_rising,
            rsi_rising=True,
            macd_hist_rising=True,
            volume_trending_up=True,
        ),
        "levels": {"nearest_support": 115_000, "nearest_resistance": 130_000},
        "trend": {"trend": "UPTREND", "strength": "strong", "momentum": "bullish"},
        "trade_setup": {
            "ticker": "FPT",
            "entry": 120_000,
            "stop": 115_000,
            "target": 140_000,
            "risk_reward": 4.0,
            "risk_reward_gross": 4.2,
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
    """Mock picks.py's get_batch_ticker_data_async + classify_strategy + sim/exit."""
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

        yield {
            "batch": mock_batch,
            "strategy": mock_strategy,
            "sim": mock_sim,
            "exit": mock_exit,
            "rsi": mock_rsi,
        }


@pytest.mark.usefixtures("mock_trading_config")
class TestTrendMomentumGate:
    """Deterministic trend-follow BUY gate — ADX strength + direction."""

    @pytest.mark.asyncio
    async def test_trend_with_rising_adx_passes(self, mock_deps):
        """TREND strategy + rising ADX → candidate retained."""
        tech = _trend_follow_tech(adx_rising=True)
        mock_deps["batch"].return_value = {"FPT": tech}
        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="TREND", confidence=0.7, matched_signals=["structural uptrend"]
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 4, 23),
            min_rr=3.0,
        )

        assert len(picks) == 1
        assert picks[0]["strategy"] == "TREND"

    @pytest.mark.asyncio
    async def test_trend_with_fading_adx_dropped(self, mock_deps):
        """TREND strategy + fading ADX → candidate dropped by gate."""
        tech = _trend_follow_tech(adx_rising=False)
        mock_deps["batch"].return_value = {"FPT": tech}
        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="TREND", confidence=0.7, matched_signals=["structural uptrend"]
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 4, 23),
            min_rr=3.0,
        )

        assert picks == []

    @pytest.mark.asyncio
    async def test_trend_with_flat_adx_passes_not_over_suppressed(self, mock_deps):
        """Flat-within-delta ADX (None) → candidate retained (do not over-suppress pullbacks)."""
        tech = _trend_follow_tech(adx_rising=None)
        mock_deps["batch"].return_value = {"FPT": tech}
        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="TREND", confidence=0.7, matched_signals=["structural uptrend"]
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 4, 23),
            min_rr=3.0,
        )

        assert len(picks) == 1

    @pytest.mark.asyncio
    async def test_momentum_with_fading_adx_dropped(self, mock_deps):
        """MOMENTUM strategy also gated — same trend-follow class."""
        tech = _trend_follow_tech(adx_rising=False)
        mock_deps["batch"].return_value = {"FPT": tech}
        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="MOMENTUM", confidence=0.8, matched_signals=["riding strength"]
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 4, 23),
            min_rr=3.0,
        )

        assert picks == []

    @pytest.mark.asyncio
    async def test_pullback_bypasses_gate(self, mock_deps):
        """PULLBACK strategy — trend-follow gate does not apply, candidate retained even with fading ADX."""
        tech = _trend_follow_tech(adx_rising=False)
        mock_deps["batch"].return_value = {"FPT": tech}
        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="PULLBACK", confidence=0.55, matched_signals=["near MA20"]
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 4, 23),
            min_rr=3.0,
        )

        assert len(picks) == 1
        assert picks[0]["strategy"] == "PULLBACK"

    @pytest.mark.asyncio
    async def test_bounce_bypasses_gate(self, mock_deps):
        """BOUNCE strategy — oversold near support, gate does not apply."""
        tech = _trend_follow_tech(adx_rising=False, supertrend_direction="DOWN")
        mock_deps["batch"].return_value = {"FPT": tech}
        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="BOUNCE", confidence=0.7, matched_signals=["oversold"]
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 4, 23),
            min_rr=3.0,
        )

        assert len(picks) == 1
