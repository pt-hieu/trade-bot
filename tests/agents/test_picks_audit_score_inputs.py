"""SWI-301: Contract test pinning every _FEATURE_KEYS scoring key to a producer in build_score_inputs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.picks_audit import build_score_inputs
from shared.rules.scoring.config import _FEATURE_KEYS

# Scoring keys with no producer today, each tracked by a Linear ticket.
# Removing a key from this allow-list requires wiring a producer in
# build_score_inputs (or the tech_data path it reads from).
# SWI-305 (v2.1.0): order_imbalance dropped from _FEATURE_KEYS; foreign_net_strength
# now reads tech_data["flow"]["foreign_net"] which picks.py injects pre-loop.
KNOWN_UNWIRED_FEATURES: dict[str, str] = {}


@pytest.fixture
def fully_populated_tech_data() -> dict:
    return {
        "trend": {"trend": "UPTREND"},
        "volume_vs_avg": 1.5,
        "rs_20d": 1.15,
        "trade_setup": {
            "valid": True,
            "risk_reward": 2.0,
            "volume_vs_avg": 1.5,
        },
    }


def test_every_scoring_feature_has_a_producer(fully_populated_tech_data):
    signal = {"ticker": "TEST", "confidence": "high"}
    setup = fully_populated_tech_data["trade_setup"]
    inputs = build_score_inputs(
        signal=signal,
        tech_data=fully_populated_tech_data,
        setup=setup,
        strategy_cls=SimpleNamespace(confidence=0.7),
        simulation=SimpleNamespace(p_target=0.55, p_stop=0.30, expected_return_pct=0.08),
        boosted={"TEST"},
        high_positive_count={"TEST": 1},
        bullish_sector_belief_count=2,
        total_sector_count=10,
    )

    for key in _FEATURE_KEYS:
        if key in KNOWN_UNWIRED_FEATURES:
            continue
        assert key in inputs, f"Scoring feature {key!r} missing from build_score_inputs output"
        value = inputs.get(key)
        assert value is not None, (
            f"Scoring feature {key!r} resolved to None — producer missing in build_score_inputs"
        )

    # Direct regression guard for SWI-301.
    assert inputs.get("rs_20d") == pytest.approx(1.15), (
        "rs_20d producer not wired through build_score_inputs"
    )


def test_flow_foreign_net_flows_to_score_inputs():
    """SWI-305 — tech_data['flow']['foreign_net'] threads into ScoreInputs."""
    tech_data = {
        "trend": {"trend": "UPTREND"},
        "volume_vs_avg": 1.5,
        "rs_20d": 1.15,
        "flow": {"foreign_net": 15e9},
    }
    inputs = build_score_inputs(
        signal={"ticker": "VHM", "confidence": "high"},
        tech_data=tech_data,
        setup={"valid": True, "risk_reward": 2.0, "volume_vs_avg": 1.5},
        bullish_sector_belief_count=2,
        total_sector_count=10,
    )
    assert inputs.get("foreign_net_strength") == pytest.approx(15e9)


def test_order_imbalance_no_longer_packed():
    """SWI-305 (v2.1.0) — order_imbalance removed from ScoreInputs."""
    inputs = build_score_inputs(
        signal={"ticker": "TEST", "confidence": "high"},
        tech_data={"flow": {"foreign_net": 10e9, "order_imbalance": 0.5}},
        setup={"valid": True, "risk_reward": 2.0},
        bullish_sector_belief_count=0,
        total_sector_count=10,
    )
    assert "order_imbalance" not in inputs
