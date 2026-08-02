"""SWI-297 — compute_score redistributes sim-feature weight when
sim_populated=False (audit rows scored before simulate_trade runs).
"""

from __future__ import annotations

import pytest

from shared.rules.scoring import (
    ScoreInputs,
    compute_score,
    load_scoring_config,
    reset_scoring_config_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_scoring_config_cache()
    yield
    reset_scoring_config_cache()


def _full_features(**overrides: object) -> ScoreInputs:
    base: ScoreInputs = {
        "risk_reward": 3.5,
        "sim_p_target": 0.6,
        "sim_p_stop": 0.3,
        "sim_ev": 8.0,
        "strategy_confidence": 0.8,
        "belief_conviction": 0.7,
        "catalyst_strength": 0.6,
        "bullish_sector_belief_count": 3,
        "total_sector_count": 10,
        "rs_20d": 1.15,
        "volume_vs_avg": 1.5,
        "trend_alignment": "UPTREND",
        "foreign_net_strength": 20e9,
    }
    base.update(overrides)  # type: ignore[arg-type]
    return base


def test_sim_populated_false_weights_sum_to_1():
    """Σ effective_weights == 1.0 after redistribution."""
    result = compute_score(features=_full_features(), regime="CALM", sim_populated=False)
    assert sum(result.weights_snapshot.values()) == pytest.approx(1.0, abs=1e-9)


def test_sim_populated_false_sim_contributions_zero():
    """All three sim breakdown entries == 0.0 when sim not populated."""
    result = compute_score(features=_full_features(), regime="CALM", sim_populated=False)
    for key in ("sim_p_target", "sim_p_stop", "sim_ev"):
        assert result.breakdown[key] == 0.0, f"{key} should be 0, got {result.breakdown[key]}"


def test_sim_populated_false_non_sim_scaled_correctly():
    """Per-feature contribution = pre-scale × (1 + w_sim/w_non_sim).

    With shipped weights w_sim=0.25, w_non_sim=0.75 → scale=1.0+0.333=1.333.
    """
    populated = compute_score(features=_full_features(), regime="CALM", sim_populated=True)
    redistributed = compute_score(features=_full_features(), regime="CALM", sim_populated=False)
    cfg = load_scoring_config()
    w_sim = sum(cfg.weights[k] for k in cfg.sim_dependent_features)
    non_sim_total = sum(v for k, v in cfg.weights.items() if k not in cfg.sim_dependent_features)
    scale = 1.0 + (w_sim / non_sim_total)
    # Compare risk_reward contribution as the load-bearing feature.
    assert redistributed.breakdown["risk_reward"] == pytest.approx(
        populated.breakdown["risk_reward"] * scale, rel=1e-3
    )


def test_sim_populated_true_matches_legacy_path():
    """sim_populated=True must reproduce the pre-fix behaviour bit-identical."""
    result_default = compute_score(features=_full_features(), regime="CALM")
    result_explicit = compute_score(features=_full_features(), regime="CALM", sim_populated=True)
    assert result_default.score == result_explicit.score
    assert result_default.breakdown == result_explicit.breakdown


def test_compute_score_persists_sim_populated():
    """ScoreResult.sim_populated reflects kwarg and round-trips through to_jsonb."""
    res_false = compute_score(features=_full_features(), regime="CALM", sim_populated=False)
    res_true = compute_score(features=_full_features(), regime="CALM", sim_populated=True)
    assert res_false.sim_populated is False
    assert res_true.sim_populated is True
    assert res_false.to_jsonb()["sim_populated"] is False
    assert res_true.to_jsonb()["sim_populated"] is True


def test_sim_populated_false_lifts_score():
    """Redistribution must raise the score for a setup with strong non-sim
    features (since the 25% sim weight no longer drags down through clipped
    defaults). Regression guard for the original SWI-297 symptom.
    """
    no_sim_features = _full_features(sim_p_target=0.0, sim_p_stop=0.5, sim_ev=0.0)
    legacy = compute_score(features=no_sim_features, regime="CALM", sim_populated=True)
    fixed = compute_score(features=no_sim_features, regime="CALM", sim_populated=False)
    assert fixed.score > legacy.score
