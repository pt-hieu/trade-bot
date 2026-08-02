"""Catalyst-position cross-reference for position-aware weekly preview.

Deterministic: cross-references active catalysts with current holdings
to identify which positions are exposed to upcoming events.
"""

from __future__ import annotations

from datetime import date

import logfire

from shared.neon.catalysts import get_active_catalysts_db
from shared.rules.catalyst_context_filter import filter_catalyst_context

# ── Impact priority ordering ───────────────────────────────────

_IMPACT_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "WATCH": 3}


def _days_until(expected) -> int | None:
    """Days from today until expected date. None if unparseable."""
    if expected is None:
        return None
    if isinstance(expected, date):
        return (expected - date.today()).days
    try:
        from datetime import datetime

        return (datetime.strptime(str(expected), "%Y-%m-%d").date() - date.today()).days
    except (ValueError, TypeError):
        return None


def _catalyst_summary(cat: dict) -> dict:
    """Extract lean summary fields from a catalyst row, including phase status."""
    from shared.rules.catalyst_lifecycle import resolve_phase_status

    summary: dict = {
        "catalyst_key": cat.get("catalyst_key"),
        "event": cat.get("event"),
        "expected": str(cat.get("expected") or ""),
        "impact": cat.get("impact") or "WATCH",
        "confidence": cat.get("confidence") or "MEDIUM",
        "days_until": _days_until(cat.get("expected")),
        "catalyst_type": cat.get("catalyst_type") or "regulatory",
        "affected_tickers": cat.get("affected_tickers") or [],
    }

    # Add phase lifecycle if catalyst has phases
    phases = cat.get("phases")
    if phases and isinstance(phases, dict):
        status = resolve_phase_status(phases)
        if status.is_relevant:
            summary["phase_lifecycle"] = status.lifecycle
            summary["phase_name"] = status.phase_name or ""
            summary["phase_behavior"] = status.behavior

    return summary


# ── Core compute ───────────────────────────────────────────────


async def compute_catalyst_preview(
    holdings: list[dict],
    lt_tickers: list[str],
    lookahead_days: int = 14,
) -> dict:
    """Cross-reference active catalysts with current holdings.

    Args:
        holdings: list[HoldingData] — one row per (ticker, plan_type) slice.
            Any ticker held under ANY plan counts as a holding for catalyst
            exposure (we fold multi-plan slices into a ticker set).
        lt_tickers: list of longterm watchlist tickers
        lookahead_days: how far ahead to scan for upcoming catalysts

    Returns:
        {position_exposure, watchlist_exposure, upcoming_week, high_impact_count}
    """
    from shared.neon.portfolio import tickers_held

    raw_catalysts: list[dict] = await get_active_catalysts_db(None)

    swing_tickers: set[str] = set(tickers_held(holdings or []))
    lt_set = set(lt_tickers)

    # SWI-20: filter the catalyst firehose to the slice this prompt actually
    # needs (universe = swing+lt), then keep only top-7 by impact/confidence/
    # days-until. Dedup + news-matching paths still consume the full set.
    universe = swing_tickers | lt_set
    with logfire.span("catalyst_preview.compute") as preview_span:
        preview_span.set_attribute("total_active", len(raw_catalysts))
        all_catalysts = filter_catalyst_context(raw_catalysts, universe)
        preview_span.set_attribute("filtered_count", len(all_catalysts))
        preview_span.set_attribute("cap_hit", len(all_catalysts) == 7)

    position_exposure: list[dict] = []
    watchlist_exposure: list[dict] = []
    upcoming_week: list[dict] = []
    high_impact_count = 0

    for cat in all_catalysts:
        affected: list[str] = cat.get("affected_tickers", [])
        market_wide = "VN-INDEX" in affected
        summary = _catalyst_summary(cat)
        days = summary["days_until"]

        # Count high-impact within lookahead window
        if cat.get("impact") == "HIGH" and days is not None and 0 <= days <= lookahead_days:
            high_impact_count += 1

        # Upcoming week list (all catalysts ≤7 days)
        if days is not None and 0 <= days <= 7:
            week_entry = dict(summary)
            week_entry["affected_tickers"] = affected
            upcoming_week.append(week_entry)

        if days is None or days > lookahead_days:
            continue

        # Position exposure — swing holdings
        matched_swing = [t for t in swing_tickers if t in affected or market_wide]
        for ticker in matched_swing:
            existing = next((e for e in position_exposure if e["ticker"] == ticker), None)
            if existing:
                existing["catalysts"].append(summary)
                if _IMPACT_ORDER.get(cat.get("impact", "WATCH"), 3) < _IMPACT_ORDER.get(
                    existing["impact"], 3
                ):
                    existing["impact"] = cat.get("impact", "WATCH")
            else:
                position_exposure.append(
                    {
                        "ticker": ticker,
                        "position_type": "swing",
                        "catalysts": [summary],
                        "impact": cat.get("impact", "WATCH"),
                    }
                )

        # Watchlist exposure — longterm tickers not already in swing
        matched_lt = [t for t in lt_set - swing_tickers if t in affected or market_wide]
        for ticker in matched_lt:
            existing = next((e for e in watchlist_exposure if e["ticker"] == ticker), None)
            if existing:
                existing["catalysts"].append(summary)
            else:
                watchlist_exposure.append({"ticker": ticker, "catalysts": [summary]})

    # Sort position_exposure by highest impact
    position_exposure.sort(key=lambda x: _IMPACT_ORDER.get(x["impact"], 3))
    # Sort upcoming_week by days_until
    upcoming_week.sort(key=lambda x: x.get("days_until") or 999)

    return {
        "position_exposure": position_exposure,
        "watchlist_exposure": watchlist_exposure,
        "upcoming_week": upcoming_week,
        "high_impact_count": high_impact_count,
        "total_active": len(raw_catalysts),
    }


# ── Outcome recording ──────────────────────────────────────────


async def record_catalyst_outcome(
    catalyst_key: str,
    outcome_detail: str,
    actual_impact: str,
    impact_score: float | None = None,
) -> None:
    """Mark a catalyst completed with outcome detail and actual impact.

    Args:
        catalyst_key: unique key of the catalyst
        outcome_detail: narrative of what actually happened
        actual_impact: e.g. 'POSITIVE', 'NEGATIVE', 'NEUTRAL'
        impact_score: optional numeric score (-1.0 to 1.0)
    """
    from shared.database import get_db

    db = await get_db()
    await db.execute(
        """UPDATE catalysts
           SET outcome_detail = $2,
               actual_impact   = $3,
               impact_score    = $4,
               status          = 'completed',
               updated_at      = NOW()
           WHERE catalyst_key = $1""",
        catalyst_key,
        outcome_detail,
        actual_impact,
        impact_score,
    )


# ── Prose formatter ────────────────────────────────────────────


def format_catalyst_preview_prose(preview: dict) -> str:
    """Format catalyst preview dict as readable text for LLM agents."""
    lines: list[str] = []

    total = preview.get("total_active", 0)
    high = preview.get("high_impact_count", 0)
    lines.append(f"CATALYST PREVIEW ({total} active, {high} high-impact within 14d)")
    lines.append("")

    # Position exposure
    pos_exp = preview.get("position_exposure", [])
    if pos_exp:
        lines.append("HOLDINGS EXPOSED:")
        for entry in pos_exp:
            ticker = entry["ticker"]
            impact = entry["impact"]
            cats = entry["catalysts"]
            lines.append(f"  {ticker} [{impact}]:")
            for c in cats:
                days = c.get("days_until")
                days_str = f"{days}d" if days is not None else "?"
                phase_label = ""
                if c.get("phase_lifecycle"):
                    phase_label = f" [{c['phase_lifecycle']}]"
                lines.append(
                    f"    • {c['event']} — {c['expected']} ({days_str}) "
                    f"[{c['confidence']} confidence]{phase_label}"
                )
    else:
        lines.append("HOLDINGS EXPOSED: none within 14 days")

    lines.append("")

    # Upcoming week
    week = preview.get("upcoming_week", [])
    if week:
        lines.append("UPCOMING 7 DAYS:")
        for c in week:
            affected = c.get("affected_tickers", [])
            tickers_str = ", ".join(affected[:10])
            if len(affected) > 10:
                tickers_str += f" +{len(affected) - 10} more"
            days = c.get("days_until")
            days_str = f"in {days}d" if days is not None else "date TBD"
            lines.append(
                f"  [{c['impact']}] {c['event']} — {days_str}"
                f"\n    Affects: {tickers_str or 'market-wide'}"
            )
    else:
        lines.append("UPCOMING 7 DAYS: no catalysts")

    lines.append("")

    # Watchlist exposure summary
    wl_exp = preview.get("watchlist_exposure", [])
    if wl_exp:
        wl_tickers = [e["ticker"] for e in wl_exp]
        lines.append(f"LONGTERM WATCHLIST EXPOSED: {', '.join(wl_tickers)}")

    return "\n".join(lines)
