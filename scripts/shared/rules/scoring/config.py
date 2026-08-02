"""Scoring config loader + validator.

Loaded from ``scripts/agents/configs/scoring.yaml``. Σw=1 invariant +
shape rules are enforced by :func:`validate_scoring_config`, called from:

  1. ``scripts/daily_scan.py`` init block — startup crash on malformed
     YAML mid-edit; mirrors ``init_trading_config()``.
  2. ``scripts/eval/scoring_health.py`` — daily smoke check.
  3. ``tests/shared/rules/test_scoring.py`` — unit tests.

NOT called at module import: pytest collection / IDE module-load /
pre-commit subprocess load this module on a malformed yaml mid-edit, and
that should not crash the runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import yaml

_FEATURE_KEYS: Final[tuple[str, ...]] = (
    "risk_reward",
    "sim_p_target",
    "sim_p_stop",
    "sim_ev",
    "strategy_confidence",
    "belief_conviction",
    "catalyst_strength",
    "bullish_sector_belief_count",
    "rs_20d",
    "volume_vs_avg",
    "trend_alignment",
    "foreign_net_strength",
)

# SemVer regex — major.minor.patch with no pre-release/build for now.
_SEMVER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d+\.\d+\.\d+$")

# Default config path — co-located with this package's parent (shared/rules/).
_DEFAULT_CONFIG_PATH: Final[Path] = Path(__file__).resolve().parents[1] / "scoring.yaml"


@dataclass(frozen=True)
class ScoringConfig:
    """Validated scoring config, loaded from scoring.yaml."""

    scoring_version: str
    threshold: int
    weights: dict[str, float]
    regime_penalty: dict[str, int]
    shock_penalty: int
    sim_dependent_features: tuple[str, ...] = field(default_factory=tuple)


_cached_config: ScoringConfig | None = None


def _coerce_weight(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("weight cannot be bool")
    if not isinstance(value, (int, float)):
        raise ValueError(f"weight must be number, got {type(value).__name__}")
    return float(value)


def load_scoring_config(path: Path | None = None) -> ScoringConfig:
    """Load + cache scoring config from YAML.

    Cache is module-level. Tests that mutate the YAML mid-process must
    call ``reset_scoring_config_cache()`` to bust the cache.
    """
    global _cached_config
    config_path = path or _DEFAULT_CONFIG_PATH
    if _cached_config is not None and path is None:
        return _cached_config

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    weights_raw = data.get("weights") or {}
    weights = {key: _coerce_weight(weights_raw[key]) for key in weights_raw}

    regime_penalty_data = data.get("regime_penalty") or {}
    regime_penalty: dict[str, int] = {}
    for key, value in regime_penalty_data.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"regime_penalty[{key}] must be int")
        regime_penalty[str(key)] = int(value)

    shock_raw = data.get("shock_penalty")
    if isinstance(shock_raw, bool) or not isinstance(shock_raw, (int, float)):
        raise ValueError("shock_penalty must be int")

    sim_dependent_raw = data.get("sim_dependent_features") or []
    if not isinstance(sim_dependent_raw, list):
        raise ValueError("sim_dependent_features must be a YAML list")
    sim_dependent_features = tuple(str(item) for item in sim_dependent_raw)

    config = ScoringConfig(
        scoring_version=str(data.get("scoring_version") or ""),
        threshold=int(data.get("threshold") or 0),
        weights=weights,
        regime_penalty=regime_penalty,
        shock_penalty=int(shock_raw),
        sim_dependent_features=sim_dependent_features,
    )
    if path is None:
        _cached_config = config
    return config


def reset_scoring_config_cache() -> None:
    """Clear the cached config so a subsequent load re-reads the YAML."""
    global _cached_config
    _cached_config = None


def validate_scoring_config(path: Path | None = None) -> None:
    """Assert scoring config is well-formed.

    Called from pipeline startup, scoring_health.py, and unit tests. NOT
    from module import (per file-level docstring). On failure raises
    ``ValueError`` with a precise message — caller decides whether to
    abort startup or report and continue.
    """
    config = load_scoring_config(path)

    if not _SEMVER_PATTERN.match(config.scoring_version):
        raise ValueError(
            f"scoring_version must be SemVer major.minor.patch, got {config.scoring_version!r}"
        )

    if not 0 <= config.threshold <= 100:
        raise ValueError(f"threshold must be in [0,100], got {config.threshold}")

    weight_keys: set[str] = set(config.weights.keys())
    expected_keys: set[str] = set(_FEATURE_KEYS)
    missing = expected_keys - weight_keys
    extra: set[str] = weight_keys - expected_keys
    if missing:
        raise ValueError(f"weights missing keys: {sorted(missing)}")
    if extra:
        raise ValueError(f"weights have unexpected keys: {sorted(extra)}")

    for key, value in config.weights.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"weight {key}={value} not in [0,1]")

    weight_sum = sum(config.weights.values())
    if abs(weight_sum - 1.0) >= 1e-9:
        raise ValueError(f"Σweights must equal 1.0 (±1e-9), got {weight_sum}")

    expected_regime_keys = {"CALM", "CAUTIOUS", "ELEVATED", "RISK_OFF"}
    regime_keys = set(config.regime_penalty.keys())
    if regime_keys != expected_regime_keys:
        raise ValueError(
            f"regime_penalty must have exactly {sorted(expected_regime_keys)}, "
            f"got {sorted(regime_keys)}"
        )
    for key, value in config.regime_penalty.items():
        if value < 0:
            raise ValueError(f"regime_penalty[{key}]={value} must be >= 0")

    if config.shock_penalty < 0:
        raise ValueError(f"shock_penalty={config.shock_penalty} must be >= 0")

    if not config.sim_dependent_features:
        raise ValueError("sim_dependent_features must be non-empty")
    sim_set: set[str] = set(config.sim_dependent_features)
    unknown_sim = sim_set - set(_FEATURE_KEYS)
    if unknown_sim:
        raise ValueError(
            f"sim_dependent_features lists non-existent features: {sorted(unknown_sim)}"
        )
