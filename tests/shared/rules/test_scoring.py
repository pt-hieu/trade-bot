"""Unit tests for the deterministic scoring framework (SWI-171).

Tests cover:
  * Σw=1 invariant + shape rules (validate_scoring_config)
  * compute_score breakdown sums match score within 1e-6
  * Regime penalty subtraction
  * Suppressor predicate (Rule 5a parity, including v4 RR_FLOOR_ELEVATED)
  * Normalize() bounds for each feature

Tests do NOT touch the database — scoring.py is pure deterministic
Python by design (the pre-commit hook enforces this).
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from shared.rules.rr_floors import RR_FLOOR_ELEVATED
from shared.rules.scoring import (
    ReliefContext,
    ScoreInputs,
    compute_score,
    is_regime_relief_eligible,
    load_scoring_config,
    reset_scoring_config_cache,
    validate_scoring_config,
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


# ── validate_scoring_config ──────────────────────────────────────────


def test_validate_scoring_config_passes_for_shipped_yaml():
    """The shipped scoring.yaml must satisfy every invariant."""
    validate_scoring_config()


def test_validate_scoring_config_rejects_weight_sum_drift(tmp_path: Path):
    yaml_text = dedent(
        """
        scoring_version: "1.0.0"
        threshold: 60
        weights:
          risk_reward: 0.30
          sim_p_target: 0.10
          sim_p_stop: 0.05
          sim_ev: 0.10
          strategy_confidence: 0.05
          belief_conviction: 0.10
          catalyst_strength: 0.14
          bullish_sector_belief_count: 0.07
          rs_20d: 0.05
          volume_vs_avg: 0.05
          trend_alignment: 0.05
          foreign_net_strength: 0.04
        regime_penalty:
          CALM: 0
          CAUTIOUS: 3
          ELEVATED: 7
          RISK_OFF: 15
        shock_penalty: 5
        """
    ).strip()
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml_text)
    with pytest.raises(ValueError, match="Σweights must equal 1.0"):
        validate_scoring_config(bad)


def test_validate_scoring_config_rejects_missing_key(tmp_path: Path):
    yaml_text = dedent(
        """
        scoring_version: "1.0.0"
        threshold: 60
        weights:
          risk_reward: 1.00
        regime_penalty:
          CALM: 0
          CAUTIOUS: 3
          ELEVATED: 7
          RISK_OFF: 15
        shock_penalty: 5
        """
    ).strip()
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml_text)
    with pytest.raises(ValueError, match="weights missing keys"):
        validate_scoring_config(bad)


def test_validate_scoring_config_rejects_bad_semver(tmp_path: Path):
    yaml_text = dedent(
        """
        scoring_version: "1.0"
        threshold: 60
        weights:
          risk_reward: 0.20
          sim_p_target: 0.10
          sim_p_stop: 0.05
          sim_ev: 0.10
          strategy_confidence: 0.05
          belief_conviction: 0.10
          catalyst_strength: 0.14
          bullish_sector_belief_count: 0.07
          rs_20d: 0.05
          volume_vs_avg: 0.05
          trend_alignment: 0.05
          foreign_net_strength: 0.04
        regime_penalty:
          CALM: 0
          CAUTIOUS: 3
          ELEVATED: 7
          RISK_OFF: 15
        shock_penalty: 5
        """
    ).strip()
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml_text)
    with pytest.raises(ValueError, match="scoring_version must be SemVer"):
        validate_scoring_config(bad)


# ── compute_score ────────────────────────────────────────────────────


def test_compute_score_sum_matches_score():
    """breakdown contributions − penalties == score (within 1e-6)."""
    result = compute_score(_full_features(), regime="CALM")
    contributions = sum(
        v for k, v in result.breakdown.items() if k not in ("regime_penalty", "shock_penalty")
    )
    expected = max(0.0, min(100.0, contributions - result.regime_penalty - result.shock_penalty))
    assert abs(expected - result.score) < 1e-3


def test_compute_score_setup_invalid_returns_zero_risk_reward():
    """Layer 1 setup_invalid → R:R=0 → low score."""
    features = _full_features(risk_reward=0.0)
    result = compute_score(features, regime="CALM")
    assert result.breakdown["risk_reward"] == 0.0


def test_compute_score_calm_regime_no_penalty():
    result = compute_score(_full_features(), regime="CALM")
    assert result.regime_penalty == 0.0


def test_compute_score_risk_off_subtracts_15():
    config = load_scoring_config()
    expected_penalty = float(config.regime_penalty["RISK_OFF"])
    result = compute_score(_full_features(), regime="RISK_OFF")
    assert result.regime_penalty == expected_penalty
    base = compute_score(_full_features(), regime="CALM")
    assert abs(base.score - result.score - expected_penalty) < 1e-3


def test_replay_v2_0_0_row_under_v2_1_0_drops_order_imbalance():
    """SWI-305 — a v2.0.0 audit row with feature_order_imbalance set must
    score deterministically under v2.1.0 (key silently ignored)."""
    legacy_features = _full_features()
    legacy_features["order_imbalance"] = 0.7  # type: ignore[typeddict-unknown-key]
    result = compute_score(legacy_features, regime="CALM")
    assert "order_imbalance" not in result.breakdown
    assert "order_imbalance" not in result.weights_snapshot
    assert result.score > 0


def test_compute_score_score_clamped_to_zero():
    """Even with 0 features and high penalty, score does not go negative."""
    empty: ScoreInputs = {}
    result = compute_score(empty, regime="RISK_OFF")
    assert result.score >= 0.0


def test_compute_score_score_clamped_to_hundred():
    """Maximal features cap at 100."""
    maxed = _full_features(
        risk_reward=10.0,
        sim_p_target=1.0,
        sim_p_stop=0.0,
        sim_ev=100.0,
        strategy_confidence=1.0,
        belief_conviction=1.0,
        catalyst_strength=1.0,
        bullish_sector_belief_count=10,
        total_sector_count=10,
        rs_20d=1.4,
        volume_vs_avg=3.0,
        trend_alignment="UPTREND",
        foreign_net_strength=100e9,
    )
    result = compute_score(maxed, regime="CALM")
    assert result.score <= 100.0


# ── Suppressor parity (v4 RR_FLOOR_ELEVATED predicate) ───────────────


def test_relief_eligible_full_predicate_passes():
    relief: ReliefContext = {
        "underlying_stress": True,
        "shock_active": False,
        "has_high_positive_macro_catalyst": True,
        "has_candidate_positive_catalyst": False,
        "bullish_sector_belief_count": 3,
        "candidate_risk_reward": RR_FLOOR_ELEVATED + 0.5,
    }
    eligible, reason = is_regime_relief_eligible("ELEVATED", relief)
    assert eligible is True
    assert reason is None


def test_relief_blocked_when_rr_below_elevated_floor():
    """v4 round-3 fix: candidate R:R must clear RR_FLOOR_ELEVATED."""
    relief: ReliefContext = {
        "underlying_stress": True,
        "shock_active": False,
        "has_high_positive_macro_catalyst": True,
        "has_candidate_positive_catalyst": False,
        "bullish_sector_belief_count": 3,
        "candidate_risk_reward": RR_FLOOR_ELEVATED - 0.5,
    }
    eligible, reason = is_regime_relief_eligible("ELEVATED", relief)
    assert eligible is False
    assert reason is not None
    assert "candidate_rr" in reason


def test_relief_blocked_under_min_bullish_beliefs():
    relief: ReliefContext = {
        "underlying_stress": True,
        "shock_active": False,
        "has_high_positive_macro_catalyst": True,
        "has_candidate_positive_catalyst": False,
        "bullish_sector_belief_count": 1,  # < 2
        "candidate_risk_reward": 4.0,
    }
    eligible, reason = is_regime_relief_eligible("ELEVATED", relief)
    assert eligible is False
    assert "bullish_beliefs" in (reason or "")


def test_relief_blocked_in_calm_regime():
    relief: ReliefContext = {
        "underlying_stress": True,
        "shock_active": False,
        "has_high_positive_macro_catalyst": True,
        "has_candidate_positive_catalyst": True,
        "bullish_sector_belief_count": 3,
        "candidate_risk_reward": 5.0,
    }
    eligible, reason = is_regime_relief_eligible("CALM", relief)
    assert eligible is False
    assert reason == "regime_not_stressed"


def test_relief_suppresses_regime_and_shock_penalty():
    relief: ReliefContext = {
        "underlying_stress": True,
        "shock_active": True,
        "has_high_positive_macro_catalyst": True,
        "has_candidate_positive_catalyst": False,
        "bullish_sector_belief_count": 3,
        "candidate_risk_reward": 4.0,
    }
    no_relief = compute_score(_full_features(), regime="ELEVATED", shock_active=True)
    with_relief = compute_score(
        _full_features(),
        regime="ELEVATED",
        relief_context=relief,
        shock_active=True,
    )
    assert no_relief.regime_penalty > 0
    assert no_relief.shock_penalty > 0
    assert with_relief.regime_penalty == 0
    assert with_relief.shock_penalty == 0
    assert with_relief.score >= no_relief.score


# ── Normalization helpers ────────────────────────────────────────────


def test_normalize_trend_alignment_known_labels():
    """Sanity that downstream consumers see deterministic feature values."""
    uptrend = compute_score(_full_features(trend_alignment="UPTREND"), regime="CALM")
    sideways = compute_score(_full_features(trend_alignment="SIDEWAYS"), regime="CALM")
    downtrend = compute_score(_full_features(trend_alignment="DOWNTREND"), regime="CALM")
    assert (
        uptrend.breakdown["trend_alignment"]
        > sideways.breakdown["trend_alignment"]
        > downtrend.breakdown["trend_alignment"]
    )
    assert downtrend.breakdown["trend_alignment"] == 0.0


def test_score_breakdown_persists_weights_snapshot():
    result = compute_score(_full_features(), regime="CALM")
    assert "weights_snapshot" in result.to_jsonb()
    snapshot = result.weights_snapshot
    assert abs(sum(snapshot.values()) - 1.0) < 1e-9
