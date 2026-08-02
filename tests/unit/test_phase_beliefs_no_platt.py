"""Verify deterministic aggregation preserves BULLISH direction without Platt scaling.

Regression test for MON-2026-04-13-003: Platt scaling with negative `a` inverted
BULLISH sub-agent beliefs into NEUTRAL, producing 0 BUY recommendations for 5
consecutive days. After removing Platt from phase_beliefs.py, sub-agent
bull_probability flows through to the aggregator without compression.
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from pipeline.phase_beliefs import post_process_beliefs


def _make_belief(
    agent_key: str,
    ticker: str,
    bull: float,
    base: float,
    bear: float,
    conviction: float = 0.6,
    direction: str = "BULLISH",
    ensemble_type: str = "sector",
) -> dict:
    return {
        "agent_key": agent_key,
        "ticker": ticker,
        "bull_probability": bull,
        "base_probability": base,
        "bear_probability": bear,
        "conviction": conviction,
        "direction": direction,
        "belief_narrative": f"{agent_key} narrative for {ticker}",
        "price_target_vnd": 30000,
        "timeframe_days": 5,
        "belief_status": "NEW",
        "ensemble_type": ensemble_type,
        "days_held": 1,
    }


@pytest.mark.asyncio
async def test_bullish_beliefs_preserved_without_platt():
    """Given 3 BULLISH sub-agents with bull=0.45, aggregation should produce
    a BULLISH deterministic_aggregator — not flatten to NEUTRAL."""
    sector_beliefs = [
        _make_belief("sector_technical", "FPT", bull=0.45, base=0.35, bear=0.20),
        _make_belief("sector_news", "FPT", bull=0.50, base=0.30, bear=0.20),
        _make_belief("sector_enrichment", "FPT", bull=0.42, base=0.38, bear=0.20),
    ]

    with (
        patch(
            "pipeline.phase_beliefs.get_all_belief_accuracy",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "pipeline.phase_beliefs.compute_empirical_base_rates",
            new_callable=AsyncMock,
            return_value={"BULLISH": 0.35, "NEUTRAL": 0.40, "BEARISH": 0.25},
        ),
        patch(
            "pipeline.phase_beliefs.insert_agent_beliefs",
            new_callable=AsyncMock,
        ) as mock_insert,
    ):
        result = await post_process_beliefs(
            scan_date=date(2026, 4, 17),
            sector_beliefs=sector_beliefs,
            position_beliefs=[],
        )

    # Deterministic aggregator should produce at least 1 belief
    assert len(result["sector"]) == 1

    aggregated = result["sector"][0]
    assert aggregated["agent_key"] == "deterministic_aggregator"

    # Bull probability should remain above base — not compressed to ~0.31
    assert aggregated["bull_probability"] > aggregated["base_probability"], (
        f"bull={aggregated['bull_probability']:.3f} should exceed "
        f"base={aggregated['base_probability']:.3f} — Platt inversion regression"
    )

    # Direction should be BULLISH (not NEUTRAL)
    assert aggregated["direction"] == "BULLISH", (
        f"Expected BULLISH, got {aggregated['direction']} — "
        f"bull={aggregated['bull_probability']:.3f}"
    )

    # insert_agent_beliefs should have been called
    assert mock_insert.called


@pytest.mark.asyncio
async def test_mixed_directions_produce_variance():
    """Given a mix of BULLISH and BEARISH sub-agents, aggregated bull_probability
    across tickers should have stddev > 0.02 (not flat)."""
    sector_beliefs = [
        # FPT: BULLISH
        _make_belief("sector_technical", "FPT", bull=0.50, base=0.30, bear=0.20),
        _make_belief("sector_news", "FPT", bull=0.45, base=0.35, bear=0.20),
        # VNM: BEARISH
        _make_belief("sector_technical", "VNM", bull=0.20, base=0.30, bear=0.50),
        _make_belief("sector_news", "VNM", bull=0.25, base=0.35, bear=0.40),
        # MWG: NEUTRAL
        _make_belief("sector_technical", "MWG", bull=0.33, base=0.34, bear=0.33),
        _make_belief("sector_news", "MWG", bull=0.35, base=0.35, bear=0.30),
    ]

    with (
        patch(
            "pipeline.phase_beliefs.get_all_belief_accuracy",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "pipeline.phase_beliefs.compute_empirical_base_rates",
            new_callable=AsyncMock,
            return_value={"BULLISH": 0.35, "NEUTRAL": 0.40, "BEARISH": 0.25},
        ),
        patch(
            "pipeline.phase_beliefs.insert_agent_beliefs",
            new_callable=AsyncMock,
        ),
    ):
        result = await post_process_beliefs(
            scan_date=date(2026, 4, 17),
            sector_beliefs=sector_beliefs,
            position_beliefs=[],
        )

    all_beliefs = result["sector"] + result["positions"]
    assert len(all_beliefs) >= 2, f"Expected >=2 tickers, got {len(all_beliefs)}"

    bulls = [float(b["bull_probability"]) for b in all_beliefs]
    mean = sum(bulls) / len(bulls)
    variance = sum((b - mean) ** 2 for b in bulls) / len(bulls)
    stddev = variance**0.5

    assert stddev > 0.02, (
        f"stddev={stddev:.4f} — aggregated output is flat, bulls={[f'{b:.3f}' for b in bulls]}"
    )
