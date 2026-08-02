"""Summary and formatting functions for catalysts and capital events."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from shared.rules.catalyst_lifecycle import PhaseStatus, resolve_phase_status
from shared.rules.catalyst_override import CatalystBoost, CatalystInput
from shared.rules.geopolitical import (
    PHASE_SEVERITY,
    PHASE_STALE_WARNING_DAYS,
)

from .catalysts import get_active_catalysts_db, get_upcoming_capital_events_db

if TYPE_CHECKING:
    from pipeline.types import GeopoliticalShockDict

logger = logging.getLogger(__name__)


def build_catalyst_inputs(raw_catalysts: list[dict]) -> list[CatalystInput]:
    """Convert raw catalyst dicts (from get_active_catalysts) to typed CatalystInput list."""
    return [
        CatalystInput(
            catalyst_key=catalyst.get("id") or "",
            event=catalyst.get("event") or "",
            impact=catalyst.get("impact") or "NEUTRAL",
            confidence=catalyst.get("confidence") or "LOW",
            affected_tickers=catalyst.get("affected") or [],
            phases=catalyst.get("phases"),
            supporting_article_count=int(catalyst.get("supporting_article_count") or 0),
            # AUDIT-2026-04-24-001 / ISSUE-2026-04-24-002: macro-blanket
            # scope classification keys off catalyst_type. Raw rows already
            # surface it via `get_active_catalysts_db` -> `catalyst_type`.
            catalyst_type=str(catalyst.get("catalyst_type") or ""),
            # SWI-204: lifecycle status used by VN-INDEX positives renderer.
            expected_status=str(catalyst.get("expected_status") or ""),
        )
        for catalyst in raw_catalysts
    ]


async def get_active_catalysts(tickers: list[str] | None = None) -> list[dict]:
    """Get active catalysts from DB, optionally filtered by affected tickers."""
    rows = await get_active_catalysts_db(tickers)
    result = []
    for r in rows:
        catalyst = {
            "id": r["catalyst_key"],
            "event": r["event"],
            "expected": r["expected"],
            "affected": r.get("affected_tickers", []),
            "impact": r["impact"],
            "confidence": r["confidence"],
            "notes": r.get("notes"),
            "status": r["status"],
            "supporting_article_count": r.get("supporting_article_count") or 0,
            # Needed by build_catalyst_inputs -> CatalystInput so
            # classify_macro_catalyst_scope can gate the fan-out
            # (AUDIT-2026-04-24-001 / ISSUE-2026-04-24-002).
            "catalyst_type": r.get("catalyst_type") or "",
            # SWI-204: lifecycle status (IMMINENT/ACTIVE/...) — drives the
            # VN-INDEX positives renderer in the macro brief.
            "expected_status": r.get("expected_status") or "",
        }
        if r.get("phases"):
            catalyst["phases"] = r["phases"]
        if r.get("source"):
            catalyst["source"] = r["source"]
        result.append(catalyst)
    return result


async def compute_catalyst_boost_set() -> dict[str, CatalystBoost]:
    """Fetch active catalysts + compute boosted-ticker dict.

    Shared between Phase 0 (main pipeline, `load_db_context`) and intraday
    catalyst revision (`phase_catalyst_revision`) — the revision pipeline
    runs without Phase 0 state, so it re-computes from scratch using this
    same helper. Single code path, no silent excepts — caller handles errors.

    Returns:
        {ticker: CatalystBoost} dict (possibly empty). Raises on DB failure.
    """
    _, boost_set = await compute_catalyst_boost_bundle()
    return boost_set


async def compute_catalyst_boost_bundle() -> tuple[list[CatalystInput], dict[str, CatalystBoost]]:
    """Variant that also returns the typed active-catalyst list.

    The typed list is needed by downstream consumers like
    ``has_high_positive_macro_blanket_catalyst`` (AUDIT-2026-04-24-001 /
    ISSUE-2026-04-24-002) so intraday revision and morning both compute
    streak-relief from the same data.
    """
    from shared.rules.catalyst_override import get_catalyst_boosted_tickers

    raw_catalysts = await get_active_catalysts()
    typed_catalysts = build_catalyst_inputs(raw_catalysts)
    return typed_catalysts, get_catalyst_boosted_tickers(typed_catalysts)


def _get_current_phase(phases: dict) -> tuple[str | None, dict | None, int]:
    """Determine current phase based on today's date.

    Delegates to resolve_phase_status() for lifecycle-aware resolution.
    Returns: (phase_name, phase_info, days_active) for backward compatibility.
    """
    status = resolve_phase_status(phases)
    return status.phase_name, status.phase_info, status.days_active


async def get_active_geopolitical_shock() -> GeopoliticalShockDict | None:
    """Get the most severe active geopolitical shock with current phase.

    Returns None if no active geopolitical catalyst exists. The shape
    matches :class:`pipeline.types.GeopoliticalShockDict` so Phase 0 can
    thread it into `fetch_macro_metrics(..., geo_shock=...)` without
    reshaping.
    """
    rows = await get_active_catalysts_db(None)

    geo_catalysts = [
        r
        for r in rows
        if (r.get("catalyst_type") or "regulatory") == "geopolitical" and r.get("phases")
    ]

    if not geo_catalysts:
        return None

    best: GeopoliticalShockDict | None = None
    best_severity = 0

    for cat in geo_catalysts:
        phase_name, phase_info, days_active = _get_current_phase(cat["phases"])
        if phase_name is None:
            continue
        severity = PHASE_SEVERITY.get(phase_name, 0)
        if severity > best_severity:
            best_severity = severity
            # Prefix notes with the most recent confirmation date so readers
            # don't interpret embedded "today" / "yesterday" phrasing as
            # current-of-scan (resolves MON-2026-04-19-002 stale weekend
            # rendering). Uses last_confirmed_at (recency); falls back to
            # added_date; omits the prefix only when both are absent.
            raw_notes = cat.get("notes") or ""
            recorded_at = cat.get("last_confirmed_at") or cat.get("added_date")
            if raw_notes and recorded_at:
                date_str = str(recorded_at)[:10]
                prefixed_notes = f"[Catalyst note — recorded {date_str}]: {raw_notes}"
            else:
                prefixed_notes = raw_notes
            candidate: GeopoliticalShockDict = {
                "phase_name": phase_name,
                "catalyst_event": (cat.get("event") or "Unknown geopolitical event"),
                "behavior": (phase_info or {}).get("behavior", ""),
                "impact": (phase_info or {}).get("impact", "NEGATIVE"),
                "affected_tickers": cat.get("affected_tickers") or [],
                "notes": prefixed_notes,
                "catalyst_key": cat.get("catalyst_key"),
                "days_active": days_active,
                "phase_stale": days_active > PHASE_STALE_WARNING_DAYS,
                # Fix 2 (2026-04-21): surface the structured factor list so
                # the geo-exposure aggregator doesn't fall back to the
                # hardcoded Hormuz mapping for new shocks.
                "catalyst_factors": list(cat.get("catalyst_factors") or []),
            }
            best = candidate

    return best


def _format_catalyst_lines(catalysts: list[dict]) -> str:
    """Format a list of catalysts into a human-readable summary string."""
    lines: list[str] = []
    for catalyst in catalysts:
        affected = catalyst.get("affected") or []
        affected_str = _format_affected_tickers(affected)

        phases = catalyst.get("phases")
        if phases:
            status = resolve_phase_status(phases)
            if status.is_relevant:
                lines.append(_format_phase_line(catalyst, status, affected_str))
                continue

        impact_emoji = _impact_emoji(catalyst["impact"])
        status_label = " [IMMINENT]" if catalyst.get("status") == "imminent" else ""
        lines.append(
            f"- {catalyst['event']}: {catalyst['expected']} ({impact_emoji}){status_label} - {affected_str}"
        )

    return "\n".join(lines)


def _catalyst_relevance_score(catalyst: dict) -> tuple[int, int, str]:
    """Sort key: (imminent, confidence_rank, event). Lower = higher priority."""
    is_imminent = 1 if catalyst.get("status") == "imminent" else 0
    confidence_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(catalyst.get("confidence") or "LOW", 2)
    return (-is_imminent, confidence_rank, catalyst.get("event") or "")


async def get_catalyst_summary(tickers: list[str] | None = None) -> str | None:
    """Get formatted summary of active catalysts for morning brief.

    Returns None when no catalysts are tracked.
    """
    catalysts = await get_active_catalysts(tickers)
    if not catalysts:
        return None
    return _format_catalyst_lines(catalysts)


async def get_filtered_catalyst_summary(
    tickers: list[str] | None = None,
    max_catalysts: int = 7,
) -> str | None:
    """Get filtered catalyst summary — only relevant catalysts for agent context.

    Filters: ticker overlap, VN-INDEX affected, imminent status, or HIGH confidence.
    Sorts: imminent first → HIGH confidence → recency.
    Returns None when no relevant catalysts found.
    """
    from shared.rules.catalyst_context_filter import filter_catalyst_context

    all_catalysts = await get_active_catalysts(None)
    if not all_catalysts:
        return None

    # SWI-20: single shared filter across all LLM-injection sites.
    universe = {ticker.upper() for ticker in (tickers or [])}
    filtered = filter_catalyst_context(all_catalysts, universe, cap=max_catalysts)
    if not filtered:
        return None
    return _format_catalyst_lines(filtered)


def format_affected_tickers(tickers: list[str], limit: int = 10) -> str:
    """Format affected tickers with overflow for large lists.

    Returns ``"market-wide"`` on empty input (useful for macro catalysts).
    Shown tickers are capped at ``limit``; overflow is appended as ``+N more``.
    """
    if not tickers:
        return "market-wide"
    if len(tickers) <= limit:
        return ", ".join(tickers)
    shown = ", ".join(tickers[:limit])
    return f"{shown} +{len(tickers) - limit} more"


# Backwards-compatible private alias for internal callers.
_format_affected_tickers = format_affected_tickers


def _impact_emoji(impact: str) -> str:
    """Convert impact string to +/-/~ emoji."""
    if impact == "POSITIVE":
        return "+"
    if impact == "NEGATIVE":
        return "-"
    return "~"


def _format_phase_line(catalyst: dict, status: PhaseStatus, affected_str: str) -> str:
    """Format a single catalyst line with lifecycle-aware phase label."""
    event = catalyst["event"]
    phase_upper = (status.phase_name or "").upper().replace("_", " ")
    impact_emoji = _impact_emoji(status.impact or catalyst.get("impact", "NEUTRAL"))
    behavior = status.behavior

    lifecycle_labels = {
        "ACTIVE": f"NOW IN {phase_upper} PHASE",
        "APPROACHING_RESOLUTION": f"{phase_upper} APPROACHING RESOLUTION",
        "RECENTLY_EXPIRED": f"{phase_upper} RECENTLY COMPLETED ({status.days_active}d ago)",
        "APPROACHING": f"{phase_upper} STARTS SOON",
    }
    label = lifecycle_labels.get(status.lifecycle, phase_upper)

    parts = [f"- {event}: {label} ({impact_emoji})"]
    if behavior:
        parts.append(f" — {behavior}")
    parts.append(f"\n  Affects: {affected_str}")
    return "".join(parts)


async def get_upcoming_events(
    tickers: list[str] | None = None,
) -> list[dict]:
    """Get upcoming capital events from DB, optionally filtered by tickers."""
    rows = await get_upcoming_capital_events_db(tickers)
    result = []
    for r in rows:
        result.append(
            {
                "id": r["event_key"],
                "ticker": r["ticker"],
                "event_type": r["event_type"],
                "description": r["description"],
                "amount": r.get("amount", ""),
                "expected_date": r["expected_date"],
                "dilution_pct": r.get("dilution_pct"),
                "impact": r["impact"],
                "source": r.get("source"),
                "status": r["status"],
            }
        )
    return result


async def get_capital_events_summary(tickers: list[str] | None = None) -> str:
    """Get formatted summary of upcoming capital events for morning brief."""
    events = await get_upcoming_events(tickers)

    if not events:
        return "No upcoming capital events tracked."

    # SWI-125 Surface 7: defensive filter for legacy pre-validator rows.
    from shared.ticker_extract import TICKER_SENTINEL_REJECTS

    lines = []
    for e in events:
        ticker = (e.get("ticker") or "").strip().upper()
        # SWI-313: belt-and-suspenders — an empty ticker would render a
        # malformed "- : ..." line. Skip explicitly in addition to the
        # sentinel-rejects filter below.
        if not ticker:
            continue
        if ticker in TICKER_SENTINEL_REJECTS:
            continue
        event_type = e.get("event_type", "")
        expected = e.get("expected_date", "")
        impact = e.get("impact", "")

        if "NEGATIVE" in impact:
            indicator = "(-)"
        elif impact == "POSITIVE":
            indicator = "(+)"
        else:
            indicator = "(?)"

        dilution = e.get("dilution_pct")
        dilution_str = f" ~{dilution:.0f}% dilution" if dilution and dilution > 0 else ""
        lines.append(f"- {ticker}: {event_type} {expected} {indicator}{dilution_str}")

    if not lines:
        return "No upcoming capital events tracked."
    return "\n".join(lines)
