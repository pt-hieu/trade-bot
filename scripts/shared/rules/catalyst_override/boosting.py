"""Per-ticker catalyst boost evaluator + helpers."""

from __future__ import annotations

import logging

from ..catalyst_lifecycle import PhaseStatus, resolve_phase_status
from .types import CatalystBoost, CatalystInput

logger = logging.getLogger(__name__)

# Confidence levels unconditionally eligible for boost
_BOOST_CONFIDENCE = {"HIGH", "MEDIUM"}

# R:R floor adjustment applied per-ticker by downstream gates.
# HIGH/POSITIVE → 0.5 discount; MEDIUM/POSITIVE → 0.25 discount; otherwise 0.
_RR_FLOOR_ADJUSTMENT_BY_CONFIDENCE: dict[str, float] = {
    "HIGH": 0.5,
    "MEDIUM": 0.25,
}

# Lifecycle states eligible for boost (HIGH/MEDIUM path).
_BOOST_LIFECYCLES = {"ACTIVE", "APPROACHING_RESOLUTION", "RECENTLY_EXPIRED", "APPROACHING"}

# Lifecycle states where LOW-confidence catalysts may exceptionally pass the
# boost gate — only the near-term pre/at-event windows, never stale LOW tags.
# Intentional subset of _BOOST_LIFECYCLES (excludes RECENTLY_EXPIRED + ACTIVE).
_BOOST_LOW_CONFIDENCE_LIFECYCLES = {"APPROACHING", "APPROACHING_RESOLUTION"}

# Minimum corroborating articles required for a LOW-confidence catalyst to
# be admitted. Single-source rumors (count < 2) are excluded even when
# attached to an upcoming event date — prevents spam promotion.
_BOOST_LOW_MIN_ARTICLES = 2


def get_catalyst_boosted_tickers(
    catalysts: list[CatalystInput],
) -> dict[str, CatalystBoost]:
    """Identify tickers boosted by active positive catalysts.

    A ticker is boosted when:
    - Catalyst impact is POSITIVE
    - Catalyst confidence is HIGH or MEDIUM
    - Catalyst has an active, approaching, or recently-expired phase

    Used for LLM context prioritization, NOT for gate bypass.

    Args:
        catalysts: List of typed catalyst inputs.

    Returns:
        {ticker: CatalystBoost} mapping. Later catalysts override earlier ones
        for the same ticker (highest phase priority wins).
    """
    boosted: dict[str, CatalystBoost] = {}

    for catalyst in catalysts:
        if catalyst["impact"] != "POSITIVE":
            continue
        confidence = catalyst["confidence"]
        if confidence not in _BOOST_CONFIDENCE and confidence != "LOW":
            logger.warning(
                "catalyst_override: unexpected confidence=%r for %s — skipping",
                confidence,
                catalyst["catalyst_key"],
            )
            continue

        rr_adjustment = _RR_FLOOR_ADJUSTMENT_BY_CONFIDENCE.get(confidence, 0.0)

        phases = catalyst.get("phases")
        if not phases:
            # Non-phased catalysts: only HIGH/MEDIUM pass. LOW without a
            # lifecycle window has no corroboration signal to anchor the
            # boost — stays out regardless of article count.
            if confidence not in _BOOST_CONFIDENCE:
                continue
            if not catalyst["affected_tickers"]:
                continue
            reason = f"{catalyst['event'][:60]} — active catalyst"
            candidate = CatalystBoost(
                ticker="",
                catalyst_key=catalyst["catalyst_key"],
                catalyst_event=catalyst["event"],
                phase_lifecycle="STATIC",
                phase_name="",
                reason=reason,
                rr_floor_adjustment=rr_adjustment,
            )
            for ticker in catalyst["affected_tickers"]:
                _upsert_boost(boosted, ticker, candidate)
            continue

        status: PhaseStatus = resolve_phase_status(phases)
        if not status.is_relevant or status.lifecycle not in _BOOST_LIFECYCLES:
            continue

        if confidence == "LOW":
            if status.lifecycle not in _BOOST_LOW_CONFIDENCE_LIFECYCLES:
                continue
            article_count = catalyst["supporting_article_count"]
            if article_count < _BOOST_LOW_MIN_ARTICLES:
                logger.info(
                    "catalyst_override: LOW catalyst %s skipped — "
                    "insufficient corroboration (%d < %d articles)",
                    catalyst["catalyst_key"],
                    article_count,
                    _BOOST_LOW_MIN_ARTICLES,
                )
                continue

        reason = _build_reason(catalyst, status)
        candidate = CatalystBoost(
            ticker="",
            catalyst_key=catalyst["catalyst_key"],
            catalyst_event=catalyst["event"],
            phase_lifecycle=status.lifecycle,
            phase_name=status.phase_name or "",
            reason=reason,
            rr_floor_adjustment=rr_adjustment,
        )
        for ticker in catalyst["affected_tickers"]:
            _upsert_boost(boosted, ticker, candidate)

    return boosted


def _lifecycle_priority(lifecycle: str) -> int:
    """Higher number = higher priority for boost.

    ``MACRO_BLANKET`` shares priority 0 with ``STATIC`` intentionally: the
    macro fan-out output is kept in its own dict (see
    ``get_macro_blanket_boosts``) so callers merge per-ticker first. The
    shared priority guarantees that if a macro-blanket entry is ever
    fed through ``_upsert_boost`` ahead of an explicit per-ticker boost,
    the ``>= candidate_priority`` guard protects the later insert —
    existing keeps, matching the plan's "explicit > blanket" rule.
    """
    return {
        "ACTIVE": 4,
        "APPROACHING_RESOLUTION": 3,
        "RECENTLY_EXPIRED": 2,
        "APPROACHING": 1,
        "STATIC": 0,
        "MACRO_BLANKET": 0,
    }.get(lifecycle, 0)


def _upsert_boost(
    boosted: dict[str, CatalystBoost],
    ticker: str,
    candidate: CatalystBoost,
) -> None:
    """Insert or upgrade a boost entry if candidate has higher lifecycle priority."""
    existing = boosted.get(ticker)
    candidate_priority = _lifecycle_priority(candidate["phase_lifecycle"])
    if existing and _lifecycle_priority(existing["phase_lifecycle"]) >= candidate_priority:
        return
    boosted[ticker] = CatalystBoost(
        ticker=ticker,
        catalyst_key=candidate["catalyst_key"],
        catalyst_event=candidate["catalyst_event"],
        phase_lifecycle=candidate["phase_lifecycle"],
        phase_name=candidate["phase_name"],
        reason=candidate["reason"],
        rr_floor_adjustment=candidate.get("rr_floor_adjustment", 0.0) or 0.0,
    )


def _build_reason(catalyst: CatalystInput, status: PhaseStatus) -> str:
    """Build human-readable reason for boost."""
    event = catalyst["event"][:60]
    phase = (status.phase_name or "").replace("_", " ").title()
    behavior = status.behavior[:80] if status.behavior else ""

    if status.lifecycle == "ACTIVE":
        return f"{event} — {phase} active now. {behavior}"
    if status.lifecycle == "APPROACHING_RESOLUTION":
        return f"{event} — {phase} approaching resolution. {behavior}"
    if status.lifecycle == "RECENTLY_EXPIRED":
        return f"{event} — {phase} recently completed ({status.days_active}d ago). {behavior}"
    if status.lifecycle == "APPROACHING":
        return f"{event} — {phase} starts soon. {behavior}"
    return f"{event} — {phase}"
