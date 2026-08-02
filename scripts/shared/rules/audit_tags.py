"""Centralized audit tag vocabulary + stripper for render boundary.

Audit tags (e.g. `[DERIVED_FROM_BELIEFS]`, `[RECONCILED_FROM_BELIEFS]`) are
intentional data-layer provenance markers written into recommendation
`rationale` / `verdict` / sector notes so reviewers can trace which
reconciliation path produced a row. They must NOT leak into user-facing
brief bodies.

This module is the single source of truth for the vocabulary. Emission
sites import the named constants; render-layer callers apply
`strip_audit_tags` right before emission.
"""

from __future__ import annotations

import re

DERIVED_FROM_BELIEFS = "[DERIVED_FROM_BELIEFS]"
RECONCILED_FROM_BELIEFS = "[RECONCILED_FROM_BELIEFS]"
NO_BELIEF_NO_REC = "[NO_BELIEF_NO_REC]"
PARTIAL_COVERAGE = "[PARTIAL_COVERAGE]"
DETERMINISTIC_ONLY = "[DETERMINISTIC_ONLY]"
AGGREGATOR_PASSTHROUGH = "[AGGREGATOR_PASSTHROUGH]"
COVERAGE_GAP_OVERRIDE = "[COVERAGE_GAP_OVERRIDE]"

AUDIT_TAGS: frozenset[str] = frozenset(
    {
        DERIVED_FROM_BELIEFS,
        RECONCILED_FROM_BELIEFS,
        NO_BELIEF_NO_REC,
        PARTIAL_COVERAGE,
        DETERMINISTIC_ONLY,
        AGGREGATOR_PASSTHROUGH,
        COVERAGE_GAP_OVERRIDE,
    }
)

_TAG_PATTERN = re.compile(r"\s*(?:" + "|".join(re.escape(tag) for tag in AUDIT_TAGS) + r")\s*")


def strip_audit_tags(text: str | None) -> str:
    """Remove every registered audit tag from `text` (position-agnostic).

    Collapses the whitespace the tag introduced so rendered output reads as
    normal prose. Returns empty string on None.
    """
    if not text:
        return ""
    cleaned = _TAG_PATTERN.sub(" ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()
