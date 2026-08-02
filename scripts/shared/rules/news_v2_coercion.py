"""Post-LLM coercion for News Pipeline v2 Stage 2 enum fields (SWI-243).

Stage 2 LLM emits raw `str` for the seven enum fields below; this module
coerces against the closed allowlist. Unknown / blank inputs become the
`unclassified` sentinel and emit ``post_llm_rule.unclassified`` via
``shared.observability_post_llm.emit_rule_outcome``. Replaces the deleted
``catalyst_classifier.py`` regex layer for v2's narrower scope.

The single source of truth for catalyst_type / narrative_type allowlists
is the migration 334 CHECK constraint (`catalyst_type_allowed`); keep the
sets here in lockstep when the constraint moves.

Counter convention: Logfire query
``post_llm_rule.unclassified rule_id LIKE 'news_v2_%'`` rolls up to the
v2 launch alarm (>5% unclassified in 24h pages).
"""

from __future__ import annotations

from typing import Literal

from shared.observability_post_llm import emit_rule_outcome
from shared.post_llm_types import RuleId

# ── Allowlists ────────────────────────────────────────────────────────────

LinkKind = Literal["EXISTING", "NEW", "NONE", "unclassified"]
Impact = Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "unclassified"]
Confidence = Literal["HIGH", "MEDIUM", "LOW", "unclassified"]
EnumType = Literal[
    "regulatory",
    "earnings",
    "macro",
    "rating",
    "geopolitical",
    "corporate_action",
    "legal",
    "commodity",
    "unclassified",
]
CapitalEventType = Literal[
    "dividend",
    "split",
    "spinoff",
    "ipo",
    "secondary",
    "buyback",
    "acquisition",
    "merger",
    "unclassified",
]

_LINK_KINDS: frozenset[str] = frozenset({"EXISTING", "NEW", "NONE"})
_IMPACT: frozenset[str] = frozenset({"POSITIVE", "NEGATIVE", "NEUTRAL"})
_CONFIDENCE: frozenset[str] = frozenset({"HIGH", "MEDIUM", "LOW"})
_TYPES: frozenset[str] = frozenset(
    {
        "regulatory",
        "earnings",
        "macro",
        "rating",
        "geopolitical",
        "corporate_action",
        "legal",
        "commodity",
    }
)
_CAPITAL: frozenset[str] = frozenset(
    {
        "dividend",
        "split",
        "spinoff",
        "ipo",
        "secondary",
        "buyback",
        "acquisition",
        "merger",
    }
)

_AGENT = "news_extractor"


def _coerce_upper(rule_id: RuleId, value: str | None, allowed: frozenset[str]) -> str:
    """Coerce to UPPER allowlist; unknown/blank → 'unclassified' + emit."""
    raw = (value or "").strip()
    upper = raw.upper()
    if upper in allowed:
        return upper
    emit_rule_outcome(
        rule_id,
        "unclassified",
        agent=_AGENT,
        reason="blank_input" if not raw else "out_of_set",
        boundary="validator",
        metadata={"raw": raw[:60]},
    )
    return "unclassified"


def _coerce_lower(rule_id: RuleId, value: str | None, allowed: frozenset[str]) -> str:
    """Coerce to lower allowlist; unknown/blank → 'unclassified' + emit."""
    raw = (value or "").strip()
    lower = raw.lower()
    if lower in allowed:
        return lower
    emit_rule_outcome(
        rule_id,
        "unclassified",
        agent=_AGENT,
        reason="blank_input" if not raw else "out_of_set",
        boundary="validator",
        metadata={"raw": raw[:60]},
    )
    return "unclassified"


# ── Public API — one function per enum field ──────────────────────────────


def coerce_link_kind(value: str | None) -> LinkKind:
    """narrative_link_kind / catalyst_link_kind → EXISTING / NEW / NONE."""
    return _coerce_upper("news_v2_link_kind", value, _LINK_KINDS)  # type: ignore[return-value]


def coerce_catalyst_impact(value: str | None) -> Impact:
    return _coerce_upper("news_v2_catalyst_impact", value, _IMPACT)  # type: ignore[return-value]


def coerce_catalyst_confidence(value: str | None) -> Confidence:
    return _coerce_upper("news_v2_catalyst_confidence", value, _CONFIDENCE)  # type: ignore[return-value]


def coerce_sentiment_confidence(value: str | None) -> Confidence:
    return _coerce_upper("news_v2_sentiment_confidence", value, _CONFIDENCE)  # type: ignore[return-value]


def coerce_catalyst_type(value: str | None) -> EnumType:
    return _coerce_lower("news_v2_catalyst_type", value, _TYPES)  # type: ignore[return-value]


def coerce_narrative_type(value: str | None) -> EnumType:
    return _coerce_lower("news_v2_narrative_type", value, _TYPES)  # type: ignore[return-value]


def coerce_capital_event_type(value: str | None) -> CapitalEventType:
    return _coerce_lower("news_v2_capital_event_type", value, _CAPITAL)  # type: ignore[return-value]
