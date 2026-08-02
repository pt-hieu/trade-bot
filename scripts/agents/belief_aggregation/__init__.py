"""Deterministic belief aggregation — weighted merging + base-rate anchoring.

Runs as post-processing after aggregator LLMs, before persistence. Public
API is re-exported from submodules:

  - weighted_aggregate_beliefs: conviction × accuracy merging
  - anchor_aggregated_belief / apply_base_rate_anchor: base-rate blend
  - FALLBACK_BASE_RATES: default base rates for tests / fresh envs
"""

from ._constants import (
    BRIER_DOWN_WEIGHT_THRESHOLD,
    BRIER_JOINT_POOL_THRESHOLD,
    DISSENT_PRESERVATION_RELAX,
    FALLBACK_BASE_RATES,
    MIN_SCORED_SOFT_FLOOR,
    current_dissent_thresholds,
)
from ._core import (
    anchor_aggregated_belief,
    apply_base_rate_anchor,
    weighted_aggregate_beliefs,
    weighted_aggregate_beliefs_with_weights,
)
from ._groups import LINKED_AGENT_GROUPS, group_calibration

__all__ = [
    "BRIER_DOWN_WEIGHT_THRESHOLD",
    "BRIER_JOINT_POOL_THRESHOLD",
    "DISSENT_PRESERVATION_RELAX",
    "FALLBACK_BASE_RATES",
    "LINKED_AGENT_GROUPS",
    "MIN_SCORED_SOFT_FLOOR",
    "current_dissent_thresholds",
    "anchor_aggregated_belief",
    "apply_base_rate_anchor",
    "group_calibration",
    "weighted_aggregate_beliefs",
    "weighted_aggregate_beliefs_with_weights",
]
