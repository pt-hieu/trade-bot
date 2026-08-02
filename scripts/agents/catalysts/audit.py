"""Catalyst-discovery rejection + coercion audit (SWI-198 Lever E)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from shared.rules.catalyst_classifier import CatalystType as ClassifierCatalystType

from .schemas import CatalystReason

logger = logging.getLogger(__name__)


async def _record_catalyst_audit(
    *,
    event: str,
    candidate_type: str,
    reason: CatalystReason | Literal["coerced"],
    scan_date: date,
    rule_corrected_type: ClassifierCatalystType | None = None,
) -> None:
    """Persist a catalyst-discovery rejection or coercion (SWI-198 Lever E).

    Lightweight audit row so retro can compute drop rate + LLM-error rate
    without scraping logs. Called from BOTH branches of the classifier —
    ``rule_corrected_type`` is None on the rejected branch, populated on
    the coerced branch.

    Fail-closed against schema absence — log + drop on any DB error so a
    missing migration never blocks a discovery run.
    """
    try:
        from shared.database import get_db

        db = await get_db()
        await db.execute(
            """INSERT INTO catalyst_rejections
                   (event, candidate_type, reason, scan_date, rule_corrected_type)
               VALUES ($1, $2, $3, $4, $5)""",
            event[:500],
            candidate_type[:50] if candidate_type else None,
            reason[:50],
            scan_date,
            rule_corrected_type[:50] if rule_corrected_type else None,
        )
    except Exception as exc:
        logger.warning("Failed to persist catalyst_rejection (%s): %s", reason, exc)
