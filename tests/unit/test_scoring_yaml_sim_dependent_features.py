"""SWI-297 — validate_scoring_config catches sim_dependent_features drift."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from shared.rules.scoring import (
    load_scoring_config,
    reset_scoring_config_cache,
    validate_scoring_config,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_scoring_config_cache()
    yield
    reset_scoring_config_cache()


def test_sim_dependent_features_loaded_from_yaml():
    cfg = load_scoring_config()
    assert cfg.sim_dependent_features, "sim_dependent_features must be non-empty in shipped YAML"
    assert "sim_p_target" in cfg.sim_dependent_features
    assert "sim_p_stop" in cfg.sim_dependent_features
    assert "sim_ev" in cfg.sim_dependent_features


_BASE_YAML = dedent(
    """
    scoring_version: "2.0.0"
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


def _valid_weights_yaml(sim_block: str) -> str:
    if sim_block:
        return _BASE_YAML + "\n" + sim_block
    return _BASE_YAML


def test_validate_rejects_unknown_sim_dependent_feature(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        _valid_weights_yaml(
            sim_block="sim_dependent_features:\n  - sim_p_target\n  - does_not_exist"
        )
    )
    with pytest.raises(ValueError, match="sim_dependent_features lists non-existent"):
        validate_scoring_config(bad)


def test_validate_rejects_missing_sim_dependent_features(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(_valid_weights_yaml(sim_block=""))
    with pytest.raises(ValueError, match="sim_dependent_features must be non-empty"):
        validate_scoring_config(bad)
