"""Single Logfire event family for post-LLM rule outcomes (SWI-206).

Flat sibling of `scripts/shared/observability.py` (which is already over
the CLAUDE.md max-LOC limit). Importing nothing from `observability.py`
keeps the future package-split of that module zero-coupled here.

Severity policy:
    kept         → no emit (avoid spam)
    coerced      → logfire.error
    rejected     → logfire.warning
    unclassified → logfire.info (override to DEBUG via emit kwarg if pre-merge baseline >10%)

Every emit also writes a stdlib log line with prefix
``post_llm_rule.<outcome> rule_id=<id> reason=<reason>`` so the
local-shell audit ritual (e.g. the legacy ``catalyst_classifier:``
grep) is preserved.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

import logfire

from shared.post_llm_types import (
    RuleBoundary,
    RuleId,
    RuleOutcome,
    RuleReason,
)

__all__ = ["emit_rule_outcome"]

_logger = logging.getLogger(__name__)


def emit_rule_outcome(
    rule_id: RuleId,
    outcome: RuleOutcome,
    *,
    agent: str,
    reason: RuleReason = None,
    fields_changed: tuple[str, ...] = (),
    boundary: RuleBoundary | None = None,
    metadata: Mapping[str, str | int | float | bool] | None = None,
    unclassified_as_debug: bool = False,
) -> None:
    """Emit a single ``post_llm_rule.<outcome>`` Logfire event + stdlib mirror.

    Args:
        rule_id: Stable identifier for the rule (e.g. ``catalyst_type``,
            ``critic_severity``, ``vnd_price``). Dashboard groups by this.
        outcome: One of the RuleOutcome literals.
        agent: Producing agent name (str). For ``belief_probabilities``
            this is currently the model class name pending sub-agent
            context threading (see SWI-207 follow-up).
        reason: Typed RuleReason literal — the typed union catches typos
            at call sites under pyright.
        fields_changed: Tuple of mutated field names for `coerced`.
        boundary: validator / persistence / classifier — defense-in-depth
            dedup key when the same rule fires at multiple call sites.
        metadata: Free-form payload (small, scalar values only).
        unclassified_as_debug: If True, route ``unclassified`` to DEBUG
            instead of INFO. Pass when measured baseline >10% to avoid
            spamming.
    """
    if outcome == "kept":
        return

    payload: dict[str, object] = {
        "rule_id": rule_id,
        "outcome": outcome,
        "agent": agent,
    }
    if reason is not None:
        payload["reason"] = reason
    if fields_changed:
        payload["fields_changed"] = list(fields_changed)
    if boundary is not None:
        payload["boundary"] = boundary
    if metadata:
        payload["metadata"] = dict(metadata)

    msg = f"post_llm_rule.{outcome}"
    # Spreading a `dict[str, object]` collides with logfire's reserved
    # underscore-prefixed kwargs (`_tags`, `_exc_info`). The runtime is
    # safe — no key in `payload` starts with `_` — so suppress at the
    # boundary rather than weakening the typed taxonomy with `Any`.
    if outcome == "coerced":
        logfire.error(msg, **payload)  # type: ignore[arg-type]
    elif outcome == "rejected":
        logfire.warning(msg, **payload)  # type: ignore[arg-type]
    else:
        if unclassified_as_debug:
            logfire.debug(msg, **payload)  # type: ignore[arg-type]
        else:
            logfire.info(msg, **payload)  # type: ignore[arg-type]

    _logger.info(
        "post_llm_rule.%s rule_id=%s reason=%s agent=%s fields=%s boundary=%s",
        outcome,
        rule_id,
        reason,
        agent,
        ",".join(fields_changed) if fields_changed else "-",
        boundary or "-",
    )
