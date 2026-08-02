"""Coordinator-vs-evaluator diff audit."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _audit_coordinator_diff(label: str, proposed: set[str], coordinated: set[str]) -> None:
    """Log tickers dropped or invented by the coordinator vs evaluator proposals."""
    dropped = proposed - coordinated
    if dropped:
        logger.info("Coordinator dropped %d proposed %s: %s", len(dropped), label, sorted(dropped))
    invented = coordinated - proposed
    if invented:
        logger.warning(
            "Coordinator invented %d %s not proposed by evaluators: %s",
            len(invented),
            label,
            sorted(invented),
        )
