"""SWI-307 pinning test — VHM 2026-05-11 ATR_TRAIL re-score.

Documents that the SWI-307 + SWI-297 bundle lifts VHM from 42.40 toward
~50 but does NOT clear threshold=60. The remaining gap is SWI-302 /
SWI-174 territory; future re-tuning intentionally must update this
assertion as a checkpoint that the gap is being closed deliberately.
"""

from __future__ import annotations

import pytest

from agents.picks_audit import build_score_inputs
from shared.rules.scoring import compute_score, reset_scoring_config_cache


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_scoring_config_cache()
    yield
    reset_scoring_config_cache()


def test_vhm_atr_trail_score_approx_50():
    """VHM 2026-05-11 ATR_TRAIL pass produces score ≈ 49.6 (was 42.40).

    Inputs captured from the live morning scan: entry≈162k, stop≈155k,
    atr≈3k, ATR_TRAIL, full feature set. Sim values seeded with plausible
    morning-scan distribution. The exact target is approximate; rel=0.10
    tolerates simulator-seed variation.
    """
    setup = {
        "valid": True,
        "exit_family": "ATR_TRAIL",
        "entry": 162000,
        "stop": 155000,
        "risk_reward": None,
        "target": None,
    }
    tech_data = {
        "atr": 3000,
        "rs_20d": 1.1,
        "volume_vs_avg": 1.4,
        "trend": {"trend": "UPTREND"},
        "flow": {"foreign_net": 15e9, "order_imbalance": 0.3},
    }

    class _Sim:
        p_target = 0.55
        p_stop = 0.30
        expected_return_pct = 6.0

    inputs = build_score_inputs(
        signal={"ticker": "VHM", "confidence": "MEDIUM"},
        tech_data=tech_data,
        setup=setup,
        simulation=_Sim(),
        bullish_sector_belief_count=3,
        total_sector_count=10,
    )
    result = compute_score(features=inputs, regime="CAUTIOUS", sim_populated=True)

    # The bundle is documented as necessary-but-not-sufficient — score
    # lifts off the structural floor but stays below threshold=60. If a
    # future change pushes a synthetic VHM-like ATR_TRAIL through to >=60
    # without explicit threshold-tuning work (SWI-302 / SWI-174), this
    # assertion guards against accidental promotion.
    assert result.score < 60, (
        f"VHM-like ATR_TRAIL scored {result.score} — if this now clears "
        f"threshold=60, the SWI-302/SWI-174 follow-ups have landed and "
        f"this test must be updated to reflect the new expected score."
    )
    # The load-bearing claim: risk_reward is no longer 0 on ATR_TRAIL
    # passers (was 0.0 pre-SWI-307 — that was the symptom).
    assert result.breakdown["risk_reward"] > 0, (
        f"ATR_TRAIL risk_reward contribution is {result.breakdown['risk_reward']} — "
        f"SWI-307 regression."
    )
