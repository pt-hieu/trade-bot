"""Linked-ensemble discovery + joint-N calibration gate.

A group (e.g., positions_*) triggers joint down-weighting only when EVERY
member's Brier exceeds the exclusion threshold. Individually each member
may look borderline; pooled they're clearly broken.
"""

from __future__ import annotations

import logging

import yaml

from shared.agent_config import CONFIGS_DIR

from ._constants import BRIER_JOINT_POOL_THRESHOLD

logger = logging.getLogger(__name__)


def _discover_linked_groups() -> dict[str, list[str]]:
    """Scan agent YAMLs for `ensemble_type` and group siblings.

    Contract: every agent in the same ensemble shares one `ensemble_type`
    value. Missing field → singleton (safe default; still subject to the
    per-agent sigmoid).
    """
    groups: dict[str, list[str]] = {}
    for config_file in sorted(CONFIGS_DIR.glob("*.yaml")):
        try:
            with config_file.open() as f:
                config = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("linked groups: skipping %s (%s)", config_file.name, exc)
            continue
        ensemble_type = config.get("ensemble_type")
        if ensemble_type and ensemble_type != "single":
            groups.setdefault(str(ensemble_type), []).append(config_file.stem)
    return groups


# YAML configs are committed to the repo — safe to cache the scan at
# module import time.
LINKED_AGENT_GROUPS: dict[str, list[str]] = _discover_linked_groups()


def group_calibration(
    calibration_stats: dict[str, dict],
) -> dict[str, tuple[float, int]]:
    """Compute joint calibration stats for each LINKED_AGENT_GROUPS entry.

    Returns `{agent_key: (group_brier, group_scored)}` for agents in a
    group that triggered joint calibration. Callers look up their
    agent_key and use the group stats for the sigmoid.
    """
    joint_overrides: dict[str, tuple[float, int]] = {}
    for group_name, members in LINKED_AGENT_GROUPS.items():
        member_stats: list[tuple[float, int]] = []
        for agent_key in members:
            stats = calibration_stats.get(agent_key) or {}
            brier_30d = stats.get("brier_30d")
            if brier_30d is not None:
                brier = float(brier_30d)
            else:
                # brier=0.0 is pathological but valid — must not collapse to 0.667.
                avg_brier = stats.get("avg_brier")
                brier = 0.667 if avg_brier is None else float(avg_brier)
            scored_raw = stats.get("scored_beliefs")
            scored = 0 if scored_raw is None else int(scored_raw)
            member_stats.append((brier, scored))

        if not member_stats:
            continue
        if not all(brier > BRIER_JOINT_POOL_THRESHOLD for brier, _ in member_stats):
            continue

        total_scored = sum(scored for _, scored in member_stats)
        if total_scored == 0:
            continue
        group_brier = sum(brier * scored for brier, scored in member_stats) / total_scored
        for agent_key in members:
            joint_overrides[agent_key] = (group_brier, total_scored)
        logger.warning(
            "Joint calibration gate fired: group=%s members=%s group_brier=%.3f group_scored=%d",
            group_name,
            members,
            group_brier,
            total_scored,
        )
    return joint_overrides
