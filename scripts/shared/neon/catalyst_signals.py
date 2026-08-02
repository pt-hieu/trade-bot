"""Catalyst spike detection for intraday strategy revision.

Compares catalyst updated_at against the most recent intraday inspection
baseline — GREATEST(daily_scans.created_at, daily_scans.last_revision_at) —
so same-day cron runs don't re-fire on already-consumed catalysts (SWI-275).
"""

from __future__ import annotations

import logging
from datetime import date

from ..database import get_db

logger = logging.getLogger(__name__)


async def detect_catalyst_spike(
    scan_date: date,
) -> tuple[bool, str, list[dict]]:
    """Detect catalysts updated since the last consumed baseline for scan_date.

    Baseline = GREATEST(daily_scans.created_at, COALESCE(last_revision_at,
    created_at)). Idempotent across same-day cron runs (SWI-275).
    Fail-closed: returns (False, ...) if morning scan hasn't run yet.

    Returns:
        (has_spike, trigger_description, changed_catalysts)
    """
    db = await get_db()

    # Baseline = most recent of morning scan or last consumed inspection.
    morning_ts = await db.fetch_val(
        """SELECT GREATEST(created_at, COALESCE(last_revision_at, created_at))
           FROM daily_scans WHERE scan_date = $1""",
        scan_date,
    )
    if morning_ts is None:
        logger.info("No morning scan found for %s — skip spike detection", scan_date)
        return False, "No morning scan data", []

    # Find catalysts updated after the consumed baseline.
    rows = await db.fetch_all(
        """SELECT catalyst_key, event, status, impact, confidence,
                  affected_tickers, phases, updated_at, catalyst_type
           FROM catalysts
           WHERE status IN ('active', 'monitoring', 'imminent')
             AND pipeline_version = 'v2'
             AND updated_at > $1
           ORDER BY updated_at DESC""",
        morning_ts,
    )

    if not rows:
        return False, "", []

    changed: list[dict] = []
    for row in rows:
        changed.append(
            {
                "catalyst_key": row["catalyst_key"],
                "event": row["event"] or "Unknown",
                "status": row["status"],
                "impact": row["impact"] or "WATCH",
                "confidence": row["confidence"] or "MEDIUM",
                "affected_tickers": row["affected_tickers"] or [],
                "catalyst_type": row["catalyst_type"] or "regulatory",
                "updated_at": str(row["updated_at"]),
            }
        )

    events = [c["event"] for c in changed[:3]]
    trigger = f"{len(changed)} catalyst(s) updated since morning scan: {', '.join(events)}"

    return True, trigger, changed


async def mark_scan_revision_completed(scan_date: date) -> None:
    """Advance the spike-detector baseline for scan_date.

    Sets daily_scans.last_revision_at = NOW() so subsequent intraday runs
    only fire on catalysts updated AFTER this inspection.
    """
    db = await get_db()
    status = await db.execute(
        "UPDATE daily_scans SET last_revision_at = NOW() WHERE scan_date = $1",
        scan_date,
    )
    # asyncpg returns a status string like "UPDATE 1"; "UPDATE 0" means the
    # daily_scans row is missing — fail loudly so the gap doesn't go unseen.
    if status.endswith(" 0"):
        logger.warning(
            "mark_scan_revision_completed: no daily_scans row for %s (status=%s)",
            scan_date,
            status,
        )
