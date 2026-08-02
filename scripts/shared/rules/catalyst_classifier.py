"""Deterministic catalyst_type reclassifier.

Defense-in-depth layer between the catalyst-discovery LLM and the DB. The
agent's YAML prompt is the primary instruction (Fix 3 — removed the
"prefer conservative classification" line and added 4 positive worked
examples), and this module is the post-pass that catches residual LLM
slippage before `upsert_catalyst` writes a wrong `catalyst_type`.

Rule priority (first match wins — order matters):
  1. Central-bank / IMF policy statement  → macro
  2. Geopolitical shock event              → geopolitical  (requires phases)
  3. Pure commodity price/supply shock     → commodity
  4. Vietnamese-government regulatory act  → regulatory
  5. No override (caller's choice stands)

Every override emits ``post_llm_rule.coerced rule_id=catalyst_type`` via
``shared.observability_post_llm.emit_rule_outcome``. Stdlib logger keeps
the grep-friendly mirror line for local audit (preserves the legacy
``catalyst_classifier:`` ritual).

Fail-closed: returns the caller's type when no rule fires. Never widens
or softens — only reclassifies clearly wrong labels (Fed tagged as
regulatory, Hormuz tagged as regulatory, etc.). First instance of the
broader "LLM → DB enum with no deterministic post-pass" pattern — see
`feedback_post_llm_rule_layer.md` for the class.
"""

from __future__ import annotations

import re
from typing import Literal

from shared.observability_post_llm import emit_rule_outcome
from shared.post_llm_types import CatalystReason, RuleOutcome

CatalystType = Literal[
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


# Rule 1 — central-bank / IMF policy statements. Subject is the policymaker,
# not the event they're commenting on. A Fed governor discussing "Iran war
# risk" is still a Fed statement → macro. SBV Deputy Governor discussing
# deposit rates is macro (monetary stance), but an SBV AML circular is
# regulatory (domestic rule-making) — the regex only catches rate/policy
# context on SBV to avoid false positives.
_MACRO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfederal reserve\b", re.I),
    re.compile(r"\bfed (?:chair|governor|president|beige book|officials?)", re.I),
    re.compile(r"\bFOMC\b"),
    re.compile(r"\bIMF\b"),
    re.compile(r"\bECB\b"),
    re.compile(r"\bBOJ\b|\bBank of Japan\b", re.I),
    re.compile(r"\bPBOC\b|People'?s Bank of China", re.I),
    re.compile(r"central bank(?:ers)?\b", re.I),
    re.compile(
        r"(?:State Bank|SBV|NHNN).*(?:deposit rate|lending rate|policy rate|monetary)",
        re.I,
    ),
    # SWI-198: IMF growth/GDP forecasts and Fed nominee politics.
    re.compile(r"\bIMF\b.*\b(?:GDP|growth|forecast)\b", re.I),
    re.compile(r"\bFed\b.*(?:nominee|chair candidate|hire|fire)", re.I),
    re.compile(r"(?:Trump|White House).*(?:Fed|Powell)", re.I),
)

# Rule 2 — geopolitical shocks. These demand a `phases` dict; the
# reclassifier rejects the write when phases is missing so the agent's
# retry loop can re-emit with the required structure. Single-word
# triggers are shared with `agents.catalysts._find_duplicate_catalyst`
# via `shared.rules.catalyst_news.GEOPOLITICAL_KEYWORDS`; multi-word
# phrases below are classification-only.
_GEOPOLITICAL_PHRASES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bforce[- ]majeure\b", re.I),
    re.compile(r"\biran(?:-|\s)(?:war|israel|russia|conflict|crisis)", re.I),
    re.compile(r"\brussia(?:n)? (?:oil|sanction)", re.I),
    re.compile(r"\bmissile (?:strike|attack)\b", re.I),
    re.compile(r"\bmilitary (?:strike|operation|action)\b", re.I),
    re.compile(r"\bmiddle[- ]east (?:conflict|crisis|war|tension|geopolitical)", re.I),
    re.compile(r"\bstrait (?:closure|blockade|disruption)\b", re.I),
    re.compile(r"\btaiwan (?:tension|strait|conflict)", re.I),
    re.compile(r"\bred sea (?:crisis|attack|disruption)", re.I),
    # SWI-198: OPEC/oil-supply geopolitical disruption coverage.
    re.compile(r"\bOPEC\+?\b"),
    re.compile(r"\b(?:UAE|Saudi|Qatar) (?:quits|leaves|exits) OPEC", re.I),
    re.compile(r"\boil supply (?:loss|cut|disruption)\b", re.I),
    re.compile(r"\bHormuz\b", re.I),
    re.compile(r"\bred sea (?:transit|attack)\b", re.I),
    re.compile(r"\bIRGC\b|\bHouthi\b", re.I),
    re.compile(r"\btanker (?:hijack|seizure)\b", re.I),
    re.compile(r"\bpetrochemical complex (?:suspends|halts)\b", re.I),
)


def _geopolitical_patterns() -> tuple[re.Pattern[str], ...]:
    """Combine multi-word phrases, morphology patterns, and word-boundary keywords.

    - `_GEOPOLITICAL_PHRASES` (local, file-top): multi-word phrases unique
      to the classifier.
    - `GEOPOLITICAL_KEYWORD_PATTERNS` (shared): morphology-aware tuple
      covering ``Iran/Iranian``, ``Russia/Russian``, ``Qatar/Qatari`` etc.
      Extending the shared tuple fixes the classifier without touching
      dedup (AUDIT-2026-04-24-001 / ISSUE-2026-04-24-004).
    - `GEOPOLITICAL_KEYWORDS` (shared set): exact-word fallback for the
      remaining single-word triggers.
    """
    from shared.rules.catalyst_news import GEOPOLITICAL_KEYWORD_PATTERNS, GEOPOLITICAL_KEYWORDS

    keyword_patterns = tuple(
        re.compile(rf"\b{re.escape(word)}\b", re.I) for word in sorted(GEOPOLITICAL_KEYWORDS)
    )
    return _GEOPOLITICAL_PHRASES + GEOPOLITICAL_KEYWORD_PATTERNS + keyword_patterns


_GEOPOLITICAL_PATTERNS: tuple[re.Pattern[str], ...] = _geopolitical_patterns()

# Rule 3 — pure commodity shock (oil, gold, steel) with no geopolitical
# driver named. Runs AFTER the geopolitical check so "oil spike from
# Hormuz" is classified geopolitical, not commodity.
_COMMODITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\boil (?:exports?|price|supply|demand)\b", re.I),
    re.compile(r"\b(?:brent|WTI) (?:crude|price)", re.I),
    re.compile(r"\bmarine fuel\b", re.I),
    re.compile(r"\bgold price\b", re.I),
    re.compile(r"\bsteel price\b", re.I),
    re.compile(r"\bcommodity (?:shock|spike|price)\b", re.I),
    re.compile(r"\biron ore price\b", re.I),
    # SWI-198: VN refinery + LNG + bulk oil supply units.
    re.compile(r"\bIdemitsu\b", re.I),
    re.compile(r"\bLong Son petrochemical\b", re.I),
    re.compile(r"\b\d+M? barrels\b", re.I),
    re.compile(r"\bLNG (?:cargo|shipment|export)\b", re.I),
)

# Rule 4 — Vietnamese-government regulatory acts. Acts only when a VN
# government actor OR decree/circular identifier is named verbatim.
_VN_REGULATORY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:Thủ tướng|Chính phủ|Ủy ban Chứng khoán|Bộ Tài chính|Bộ Công Thương|"
        r"Quốc hội|NHNN|SBV)\b"
    ),
    re.compile(r"\bNghị định\b|\bQuyết định\b|\bThông tư\b", re.I),
    re.compile(
        r"\b(?:Prime Minister|Finance Minister|State Bank of Vietnam|Ministry of "
        r"Finance|Ministry of Industry|National Assembly|Securities Commission)\b",
        re.I,
    ),
    re.compile(r"\b(?:Decree|Resolution|Circular|Directive)\s+\d+[A-Za-z]?", re.I),
)


def classify_catalyst_type(
    event: str,
    candidate_type: str,
    has_phases: bool,
) -> tuple[CatalystType, RuleOutcome, CatalystReason | None]:
    """Return (effective_type, outcome, reason).

    ``candidate_type`` is the agent-proposed type. ``has_phases`` indicates
    whether the caller also supplied a phases dict (required when the
    classifier wants to flip to ``geopolitical``). Unknown or empty
    candidates default to ``regulatory`` (legacy compatibility).

    Outcomes:
      * ``("...", "kept", None)`` — candidate unchanged. Caller writes as-is.
      * ``("...", "coerced", reason)`` — type was overridden; ``reason``
        carries the rule that fired.
      * ``(<candidate>, "rejected", "missing_phases")`` — classifier wanted
        ``geopolitical`` but caller omitted ``phases``. Caller should reject
        the write so the agent retry loop re-emits with phases. The caller
        fork at ``agents/catalysts.py`` keys on this exact pair.

    Grep ``post_llm_rule.coerced rule_id=catalyst_type`` for audit.
    """
    raw_candidate = (candidate_type or "").strip().lower()
    candidate = raw_candidate or "regulatory"
    safe_candidate: CatalystType = (
        candidate if candidate in _VALID_TYPES else "regulatory"  # type: ignore[assignment]
    )
    # SWI-198: distinguish "agent declared regulatory" from "agent gave us
    # nothing → fell back to regulatory". The latter becomes the
    # ``unclassified`` sentinel when no rule fires, so consumers can filter.
    candidate_was_blank = not raw_candidate

    # Rule 1 — macro
    if _any_match(event, _MACRO_PATTERNS):
        if safe_candidate != "macro":
            _emit_coerced("macro_subject", event, safe_candidate, "macro")
            return "macro", "coerced", "macro_subject"
        return "macro", "kept", None

    # Rule 2 — geopolitical (with phases requirement)
    if _any_match(event, _GEOPOLITICAL_PATTERNS):
        if not has_phases and safe_candidate != "geopolitical":
            emit_rule_outcome(
                "catalyst_type",
                "rejected",
                agent="catalyst_classifier",
                reason="missing_phases",
                boundary="classifier",
                metadata={"event": _trim(event), "candidate": safe_candidate},
            )
            return safe_candidate, "rejected", "missing_phases"
        if safe_candidate != "geopolitical":
            _emit_coerced("geopolitical_subject", event, safe_candidate, "geopolitical")
            return "geopolitical", "coerced", "geopolitical_subject"
        return "geopolitical", "kept", None

    # Rule 3 — commodity (only after geopolitical ruled out)
    if _any_match(event, _COMMODITY_PATTERNS):
        if safe_candidate not in ("commodity", "geopolitical"):
            _emit_coerced("commodity_subject", event, safe_candidate, "commodity")
            return "commodity", "coerced", "commodity_subject"
        return safe_candidate, "kept", None

    # Rule 4 — VN regulatory. Tighten: we only OVERRIDE when candidate is
    # something clearly wrong (e.g. macro) and a VN actor is named. Most
    # VN regulatory rows already carry the correct tag — we don't want to
    # thrash `earnings`/`rating`/`corporate_action` into `regulatory`.
    if safe_candidate in ("macro", "geopolitical", "commodity") and _any_match(
        event, _VN_REGULATORY_PATTERNS
    ):
        _emit_coerced("vn_regulatory_subject", event, safe_candidate, "regulatory")
        return "regulatory", "coerced", "vn_regulatory_subject"

    # SWI-198: no rule fired. When the agent gave us nothing (blank candidate
    # collapsed to "regulatory" default), emit the ``unclassified`` sentinel
    # instead of persisting a fake regulatory row. When the agent explicitly
    # typed something we trust it.
    if candidate_was_blank:
        _emit_coerced("unclassified_default", event, safe_candidate, "unclassified")
        return "unclassified", "coerced", "unclassified_default"
    return safe_candidate, "kept", None


def _emit_coerced(
    reason: CatalystReason,
    event: str,
    from_type: str,
    to_type: str,
) -> None:
    emit_rule_outcome(
        "catalyst_type",
        "coerced",
        agent="catalyst_classifier",
        reason=reason,
        fields_changed=("catalyst_type",),
        boundary="classifier",
        metadata={"event": _trim(event), "from": from_type, "to": to_type},
    )


# Allowlist mirror of migration 334's CHECK constraint
# (`catalyst_type_allowed`). Drift guard test asserts these stay in lockstep.
_VALID_TYPES: frozenset[str] = frozenset(
    {
        "regulatory",
        "earnings",
        "macro",
        "rating",
        "geopolitical",
        "corporate_action",
        "legal",
        "commodity",
        "unclassified",
    }
)


def _any_match(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(p.search(text) for p in patterns)


def _trim(event: str) -> str:
    """Truncate long event strings for audit log readability."""
    return event if len(event) <= 80 else event[:77] + "..."
