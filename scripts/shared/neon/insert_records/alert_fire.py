"""Public seam for the alert→BUY closure path (SWI-NN).

Callers in `run_alert_analysis.py` use this entrypoint instead of reaching
into `_common._INSERT_REC_SQL` / `_build_rec_row` directly. The new
`check_neon_private_import` hook blocks the boundary violation on next attempt.

SWI-266 follow-up #4 (full hoist of `_INSERT_REC_SQL` / `_build_rec_row` to a
public API) remains [DEF] — this seam closes the specific alert_fire boundary
gap without growing the public surface.
"""

from __future__ import annotations

import logging

from ...database import execute as _execute
from .._error_guard import narrow_db_error
from ._common import _INSERT_REC_SQL, _build_rec_row

logger = logging.getLogger(__name__)


async def insert_alert_fire_recommendation(
    record_id: int,
    rec: dict,
    vn_universe: frozenset[str] | None,
) -> bool:
    """Insert a single `source='alert_fire'` rec idempotently.

    Wraps `_build_rec_row` + `_INSERT_REC_SQL` execute. `uniq_daily_recs_alert_fire`
    (migration 342) gives us idempotency on retried alert fires.

    Returns True on success, False when `_build_rec_row` rejects the ticker/row.
    """
    row = _build_rec_row(int(record_id), rec, vn_universe)
    if row is None:
        logger.warning(
            "insert_alert_fire_recommendation: _build_rec_row rejected ticker=%r",
            rec.get("ticker"),
        )
        return False
    try:
        await _execute(_INSERT_REC_SQL + " ON CONFLICT DO NOTHING", *row)
    except Exception as exc:
        narrow_db_error(
            exc,
            context=f"insert_alert_fire_recommendation ticker={rec.get('ticker')!r}",
        )
        return False
    return True
