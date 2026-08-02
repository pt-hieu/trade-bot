"""Read/write helpers for daily_records.streak_alert_json.

Single derivation path between retro (writer) and the next morning
brief (reader). Blob shape (migration 311):
    {"length": int, "start_date": str, "gate_profile": str}
"""

from __future__ import annotations

import json
import logging
from datetime import date

from ..database import get_db
from ._error_guard import narrow_db_error

logger = logging.getLogger(__name__)


async def upsert_streak_alert(scan_date: date, alert_json: dict | None) -> None:
    """Persist (or clear) the streak alert blob for the given scan date.

    Passing ``alert_json=None`` clears the column (legitimate "no streak"
    state). Pass the dict produced by ``StreakAlert.to_jsonb()`` otherwise.

    Write timing: retro of Day N writes the row whose ``record_date = N``.
    The matching morning-gate snapshot lives in the *Day N+1* row's
    ``gate_decision_json.inputs_digest.streak_alert``. See
    ``agents/retro/streak.py::detect_zero_buy_streak`` for the full T-1 /
    T-0 snapshot semantics (SWI-125 Surface 3).
    """
    db = await get_db()
    payload = json.dumps(alert_json) if alert_json is not None else None
    try:
        # IS DISTINCT FROM avoids a row-touch when writing NULL-over-NULL
        # (the no-streak path runs daily and would otherwise UPDATE every row).
        await db.execute(
            """
            UPDATE daily_records
            SET streak_alert_json = $1::jsonb
            WHERE record_date = $2
              AND streak_alert_json IS DISTINCT FROM $1::jsonb
            """,
            payload,
            scan_date,
        )
    except Exception as exc:
        narrow_db_error(exc, context=f"upsert_streak_alert scan_date={scan_date}")


async def get_streak_alert(scan_date: date) -> dict | None:
    """Return the persisted streak alert blob for `scan_date`, or None."""
    db = await get_db()
    try:
        row = await db.fetch_one(
            "SELECT streak_alert_json FROM daily_records WHERE record_date = $1",
            scan_date,
        )
    except Exception as exc:
        narrow_db_error(exc, context=f"get_streak_alert scan_date={scan_date}")
        return None
    if not row:
        return None
    blob = row["streak_alert_json"]
    if blob is None:
        return None
    if isinstance(blob, str):
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            logger.warning("Malformed streak_alert_json for %s — ignoring", scan_date)
            return None
    return dict(blob) if isinstance(blob, dict) else None
