"""Deterministic 0-100 BUY-candidate scoring framework.

Pure-Python package — single source of truth for feature weights,
normalization math, threshold, and regime/shock-penalty math. No async,
no DB, no LLM calls. Pre-commit guard
(``scripts/hooks/check_no_async_in_scoring.py``) enforces this rule by
walking every ``.py`` file under this package.

Score formula::

    base_score   = 100 * Σ (w_i × normalize(feature_i))
    relief       = is_regime_relief_eligible(regime, …, candidate_rr)
    regime_pen   = 0 if relief else regime_penalty[regime]
    shock_pen    = 0 if relief else (shock_penalty if shock_active else 0)
    final_score  = clamp(base_score - regime_pen - shock_pen, 0, 100)

Module layout (post-modularisation, SWI-212):
  * ``config.py`` — YAML loader, ScoringConfig, validator, _FEATURE_KEYS.
  * ``normalizers.py`` — per-feature 0-1 normalizers + _NORMALIZERS registry.
  * ``relief.py`` — regime-relief eligibility (mirror of composer Rule 5a).
  * ``__init__.py`` — public API: types, ScoreResult, compute_score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .config import (
    _FEATURE_KEYS,
    ScoringConfig,
    load_scoring_config,
    reset_scoring_config_cache,
    validate_scoring_config,
)
from .normalizers import (
    _NORMALIZERS,
    CatalystStrengthInputs,
    ScoreInputs,
    _clamp,
    _normalize_bullish_count,
)
from .relief import (
    ReliefContext,
    is_regime_relief_eligible,
)

ScoringPhase = Literal["morning", "midday", "retro"]
GatedBy = Literal[
    "setup_invalid",
    "trend_momentum",
    "atr_trail_rr_gate",
    "rr_floor",
    "sizing_floor",
    "validator_max_picks",
    "passed",
]
MissKind = Literal["score_below_threshold", "no_resolvable_setup"]


@dataclass(frozen=True)
class ScoreResult:
    """Output of :func:`compute_score`.

    ``breakdown`` carries per-feature contribution points, the regime/shock
    penalties, and (when stress is present) the relief decision so audit
    rows answer "why did this candidate score N" without recomputing.
    """

    score: float
    base_score: float
    regime_penalty: float
    shock_penalty: float
    relief_suppressed: bool
    relief_block_reason: str | None
    breakdown: dict[str, float] = field(default_factory=dict)
    weights_snapshot: dict[str, float] = field(default_factory=dict)
    threshold: int = 0
    scoring_version: str = ""
    sim_populated: bool = True

    def to_jsonb(self) -> dict[str, object]:
        """Serialize for `pre_gate_candidates.breakdown` jsonb persistence."""
        return {
            "score": self.score,
            "base_score": self.base_score,
            "regime_penalty": self.regime_penalty,
            "shock_penalty": self.shock_penalty,
            "relief_suppressed": self.relief_suppressed,
            "relief_block_reason": self.relief_block_reason,
            "breakdown": dict(self.breakdown),
            "weights_snapshot": dict(self.weights_snapshot),
            "threshold": self.threshold,
            "scoring_version": self.scoring_version,
            "sim_populated": self.sim_populated,
        }


def compute_score(
    features: ScoreInputs,
    regime: str,
    relief_context: ReliefContext | None = None,
    shock_active: bool = False,
    config: ScoringConfig | None = None,
    sim_populated: bool = True,
) -> ScoreResult:
    """Compute the deterministic 0-100 score for a candidate.

    All arithmetic is here. The function does NOT touch DB, async, LLM,
    or mutate the candidate dict.

    Args:
        features: Raw feature values (see ScoreInputs). Missing keys map
            to 0 so callers can score setup_invalid drops.
        regime: Global risk regime string. CRISIS is rejected at the
            composer; passing it here returns score=0 with a note.
        relief_context: Inputs for the regime-relief suppressor predicate.
            Required to evaluate relief; if None, no relief fires (the
            conservative default for callers without context).
        shock_active: Whether an active geopolitical-shock phase is
            pinning the regime today.
        config: Optional override for testing. Defaults to module cache.

    Returns:
        ScoreResult with score, base_score, breakdown, penalty splits,
        and relief decision.
    """
    scoring_config = config or load_scoring_config()
    weights = scoring_config.weights

    # When an audit row is scored before simulate_trade has run (L1/L2
    # drops), zero the sim-feature contributions and redistribute their
    # weight across the non-sim features so the row reflects the
    # candidate's real signal strength rather than a baked-in penalty
    # from sim feature defaults.
    sim_dependent_features: tuple[str, ...] = tuple(scoring_config.sim_dependent_features)
    if not sim_populated and sim_dependent_features:
        non_sim_keys = tuple(k for k in _FEATURE_KEYS if k not in sim_dependent_features)
        sim_weight_sum = sum(weights.get(k, 0.0) for k in sim_dependent_features)
        non_sim_weight_sum = sum(weights.get(k, 0.0) for k in non_sim_keys)
        if non_sim_weight_sum <= 0:
            raise ValueError(
                f"compute_score: sim_populated=False but non-sim weight sum is "
                f"{non_sim_weight_sum} (weights={weights}, regime={regime}). "
                f"Validator should have caught this."
            )
        redistribution_scale = 1.0 + (sim_weight_sum / non_sim_weight_sum)
        weights = {
            **{k: 0.0 for k in sim_dependent_features},
            **{k: weights[k] * redistribution_scale for k in non_sim_keys},
        }

    # Per-feature contribution points: 100 × weight × normalized value.
    breakdown: dict[str, float] = {}
    total_normalized = 0.0
    for key in _FEATURE_KEYS:
        weight = weights.get(key, 0.0)
        if key == "bullish_sector_belief_count":
            normalized = _normalize_bullish_count(
                int(features.get("bullish_sector_belief_count") or 0),
                int(features.get("total_sector_count") or 0),
            )
        else:
            normalizer = _NORMALIZERS.get(key)
            raw = features.get(key)  # type: ignore[misc]
            normalized = normalizer(raw) if normalizer is not None else 0.0  # type: ignore[operator]
        contribution = 100.0 * weight * normalized
        breakdown[key] = round(contribution, 4)
        total_normalized += weight * normalized

    base_score = 100.0 * total_normalized

    # Regime + shock penalties, with relief suppressor.
    regime_pen_raw = float(scoring_config.regime_penalty.get(regime, 0))
    shock_pen_raw = float(scoring_config.shock_penalty) if shock_active else 0.0

    relief_eligible = False
    relief_block_reason: str | None = None
    if relief_context is not None:
        relief_eligible, relief_block_reason = is_regime_relief_eligible(regime, relief_context)
    else:
        relief_block_reason = "no_relief_context_provided"

    regime_pen = 0.0 if relief_eligible else regime_pen_raw
    shock_pen = 0.0 if relief_eligible else shock_pen_raw

    breakdown["regime_penalty"] = -round(regime_pen, 4)
    breakdown["shock_penalty"] = -round(shock_pen, 4)

    final = _clamp(base_score - regime_pen - shock_pen, 0.0, 100.0)

    return ScoreResult(
        score=round(final, 4),
        base_score=round(base_score, 4),
        regime_penalty=round(regime_pen, 4),
        shock_penalty=round(shock_pen, 4),
        relief_suppressed=relief_eligible,
        relief_block_reason=relief_block_reason,
        breakdown=breakdown,
        weights_snapshot=dict(weights),
        threshold=scoring_config.threshold,
        scoring_version=scoring_config.scoring_version,
        sim_populated=sim_populated,
    )


__all__ = [
    "CatalystStrengthInputs",
    "GatedBy",
    "MissKind",
    "ReliefContext",
    "ScoreInputs",
    "ScoreResult",
    "ScoringConfig",
    "ScoringPhase",
    "compute_score",
    "is_regime_relief_eligible",
    "load_scoring_config",
    "reset_scoring_config_cache",
    "validate_scoring_config",
]
