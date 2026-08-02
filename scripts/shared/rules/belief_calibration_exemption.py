"""Belief calibration exemption authority.

Phase 2 §2.5 — three distinct mechanisms cause an agent's beliefs to
bypass calibration sigmoid weight reduction; conflating them in audit
review masks where the actual mechanism fired:

  1. **Aggregator double-counting filter** at
     ``phase_beliefs.py:48`` — agents whose beliefs ARE aggregations of
     other agents (sector_aggregator, positions_aggregator) are filtered
     OUT before deterministic aggregation runs. They never reach the
     sigmoid because including them double-counts the same sub-agent
     evidence. This is a pre-aggregation filter, NOT a sigmoid exemption.

  2. **Brier sigmoid threshold** at
     ``agents/belief_aggregation/_core.py`` — agents with
     ``brier ≤ 0.65`` retain full weight regardless of `scored`. Above
     0.65, weight reduces via ``(brier - 0.65) / 0.4 * sigmoid(scored - 18)``.

  3. **Cold-start floor** at the same site — when ``scored < 18`` (less
     than 18 historically scored beliefs), the sigmoid returns 1.0 even
     when brier > 0.65. Avoids unstable weight reduction on tiny samples.

This module is the structured allowlist for mechanism 1: ``ensemble_role:
aggregator`` lives in YAML config, ``is_aggregator_double_counter(agent_key)``
reads it once at import. Mechanisms 2 and 3 are policy-level constants
in ``_constants.py`` / ``_core.py`` and stay there.

The plan deliberately introduces ``ensemble_role`` as a NEW yaml field
distinct from ``ensemble_type``. The latter is already used for joint-N
group pooling (``_groups.py``) and sector-vs-positions DB routing
(``phase_beliefs.py:155``); reusing it for aggregator filtering would
create phantom joint-groups and pool unrelated Brier scores.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


_AGENT_CONFIGS_DIR = Path(__file__).resolve().parents[2] / "agents" / "configs"


def _scan_aggregator_keys() -> frozenset[str]:
    """Scan ``scripts/agents/configs/*.yaml`` for ``ensemble_role: aggregator``.

    Reads at import time and caches the result. The set is small (today
    just sector_aggregator + positions_aggregator) and changes only when
    a new aggregator config is added — re-import to refresh.
    """
    keys: set[str] = set()
    if not _AGENT_CONFIGS_DIR.is_dir():
        logger.warning(
            "belief_calibration_exemption: agent configs dir not found at %s — "
            "no aggregators registered",
            _AGENT_CONFIGS_DIR,
        )
        return frozenset()

    for path in sorted(_AGENT_CONFIGS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except (yaml.YAMLError, OSError) as exc:
            logger.warning(
                "belief_calibration_exemption: failed to parse %s: %s",
                path.name,
                exc,
            )
            continue
        if not isinstance(data, dict):
            continue
        role = data.get("ensemble_role")
        if isinstance(role, str) and role.strip().lower() == "aggregator":
            agent_key = data.get("agent_key")
            if isinstance(agent_key, str) and agent_key:
                keys.add(agent_key)
    return frozenset(keys)


_AGGREGATOR_KEYS: frozenset[str] = _scan_aggregator_keys()


def is_aggregator_double_counter(agent_key: str) -> bool:
    """True when the agent must be filtered before aggregation to avoid
    double-counting member beliefs (mechanism #1 in Fix 6's three-mechanism
    audit). Distinct from ``should_down_weight_for_brier`` (mechanism #2):

    - ``is_aggregator_double_counter``: structural — aggregators emit
      beliefs that are themselves derived from member beliefs already in
      the pool, so re-aggregating them double-counts. Filter at source.
    - ``should_down_weight_for_brier``: probabilistic — agents whose
      Brier exceeds the uninformed-forecaster anchor receive a graduated
      weight reduction.

    """
    return agent_key in _AGGREGATOR_KEYS


def should_down_weight_for_brier(brier: float, scored: int) -> bool:
    """True when calibration mechanism #2 (Brier-based down-weight) should
    apply — i.e. the agent is past the cold-start floor AND its Brier
    exceeds the uninformed-forecaster anchor. Pure-function companion to
    ``is_aggregator_double_counter``; used for audit/explanation, not for
    the live weight reduction (which lives in ``_core._sigmoid_weight_reduction``).
    """
    from agents.belief_aggregation._constants import (
        MIN_SCORED_SOFT_FLOOR,
        current_brier_down_weight_threshold,
    )

    return scored >= MIN_SCORED_SOFT_FLOOR and brier > current_brier_down_weight_threshold()


def aggregator_keys() -> frozenset[str]:
    """Return the cached aggregator-key allowlist (debugging/audit use)."""
    return _AGGREGATOR_KEYS


__all__ = [
    "aggregator_keys",
    "is_aggregator_double_counter",
    "should_down_weight_for_brier",
]
