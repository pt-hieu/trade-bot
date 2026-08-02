"""Daily retrospective record inserts (evaluations, midday, violations, rotation/macro).

ATOMICITY (SWI-NN, 2026-05-11): the parent `daily_records` UPSERT + child
`daily_recommendations` / `daily_evaluations` writes all live inside ONE
transaction (`_insert_recs_and_evals_atomic`). A CHECK violation or UNIQUE
collision rolls back the parent too, so a failed retro no longer leaves an
orphan `daily_records` row that downstream consumers mistake for a healthy
day (the 2026-05-07 0-rec wipeout pattern, scoped to daily.py).

Ancillary writes (midday_data, midday_summaries, mode_violations, rotation,
macro) stay in `_insert_ancillary_best_effort` — each carries its own
ON CONFLICT DO NOTHING / DELETE+INSERT semantics for local idempotency, and
they are non-load-bearing for the rec/eval invariant.

The original 2026-04-19 fix (`72ac5bf8`) introduced EVAL_PERSISTENCE_GAP +
DELETE-inside-txn; that guard is preserved verbatim inside the atomic helper.
"""

from __future__ import annotations

import logging
from datetime import date

from ...database import get_db
from ...vn_universe import VNUniverseUnavailable, load_vn_universe_async
from .._error_guard import narrow_db_error
from .._sync import make_sync
from ._common import (
    _INSERT_REC_SQL,
    INSERT_EVAL_SQL,
    _build_eval_row,
    _build_rec_row,
    _normalize_trading_mode,
)

logger = logging.getLogger(__name__)


async def _insert_recs_and_evals_atomic(
    db,
    scan_date: date,
    data: dict,
    trading_mode: str | None,
    mode_compliance: bool,
    vn_universe: frozenset[str] | None,
) -> int:
    """Parent UPSERT + child rec/eval writes in ONE transaction.

    Returns the record_id so the caller's ancillary writes can fan out.
    Raises EVAL_PERSISTENCE_GAP RuntimeError when recs exist but evals do not
    (preserved verbatim from `72ac5bf8`).
    """
    day_summary = data.get("day_summary") or {}

    async with db.transaction() as conn:
        record_id = await conn.fetchval(
            """
            INSERT INTO daily_records (
                record_date, market_regime, total_recs, entry_hit_rate, win_rate,
                best_call, worst_call, key_insight, trading_mode, mode_compliance,
                global_risk_regime
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (record_date) DO UPDATE SET
                market_regime = COALESCE(EXCLUDED.market_regime, daily_records.market_regime),
                total_recs = EXCLUDED.total_recs,
                entry_hit_rate = EXCLUDED.entry_hit_rate, win_rate = EXCLUDED.win_rate,
                best_call = EXCLUDED.best_call, worst_call = EXCLUDED.worst_call,
                key_insight = EXCLUDED.key_insight, trading_mode = EXCLUDED.trading_mode,
                mode_compliance = EXCLUDED.mode_compliance,
                global_risk_regime = COALESCE(
                    EXCLUDED.global_risk_regime, daily_records.global_risk_regime
                )
            RETURNING id
            """,
            scan_date,
            data.get("market_regime"),
            day_summary.get("total_recs"),
            day_summary.get("entry_hit_rate"),
            day_summary.get("win_rate"),
            day_summary.get("best_call"),
            day_summary.get("worst_call"),
            day_summary.get("key_insight"),
            trading_mode,
            mode_compliance,
            data.get("global_risk_regime"),
        )

        rec_rows = [
            row
            for rec in data.get("recommendations", [])
            if (row := _build_rec_row(record_id, rec, vn_universe)) is not None
        ]
        eval_rows: list[tuple] = [
            row
            for eval_data in data.get("evaluations", [])
            if (row := _build_eval_row(record_id, eval_data)) is not None
        ]

        existing_rec_count = await conn.fetchval(
            "SELECT COUNT(*) FROM daily_recommendations WHERE record_id = $1",
            record_id,
        )
        recs_will_exist = bool(rec_rows) or (existing_rec_count and existing_rec_count > 0)
        if recs_will_exist and not eval_rows:
            raise RuntimeError(
                f"EVAL_PERSISTENCE_GAP scan_date={scan_date} "
                f"existing_recs_in_db={existing_rec_count} "
                f"incoming_rec_rows={len(rec_rows)} incoming_eval_rows=0 — "
                f"refusing to DELETE evaluations and leave the day unevaluated."
            )

        await conn.execute("DELETE FROM daily_recommendations WHERE record_id = $1", record_id)
        await conn.execute("DELETE FROM daily_evaluations WHERE record_id = $1", record_id)
        if rec_rows:
            await conn.executemany(_INSERT_REC_SQL, rec_rows)
        if eval_rows:
            await conn.executemany(INSERT_EVAL_SQL, eval_rows)

    return record_id


async def _insert_ancillary_best_effort(db, record_id: int, data: dict) -> None:
    """Midday / summary / violations / rotation / macro writes.

    These rows are NOT load-bearing for the rec/eval invariant; each statement
    carries its own ON CONFLICT DO NOTHING or DELETE+INSERT semantics. Kept
    outside the atomic helper so a partial failure here does not roll back
    the day's recs.
    """
    midday_data = data.get("midday_data") or {}
    if midday_data:
        from .._afternoon_plan_serde import serialize_afternoon_plan

        afternoon_plan_json = serialize_afternoon_plan(
            midday_data.get("afternoon_plan"),
            context=f"insert_daily_record record_id={record_id}",
        )
        await db.execute(
            """INSERT INTO midday_data (record_id, trading_mode, entries_hit, afternoon_plan)
               VALUES ($1, $2, $3, $4::jsonb)
               ON CONFLICT (record_id) DO NOTHING""",
            record_id,
            midday_data.get("trading_mode"),
            len(entries_hit)
            if isinstance((entries_hit := midday_data.get("entries_hit")), list)
            else (entries_hit or 0),
            afternoon_plan_json,
        )

    midday_summary = data.get("midday_summary") or {}
    if midday_summary:
        await db.execute("DELETE FROM midday_summaries WHERE record_id = $1", record_id)
        await db.execute(
            """
            INSERT INTO midday_summaries (
                record_id, adjustments_made, adjustments_helpful,
                adjustments_harmful, afternoon_accuracy, key_adjustment
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
            record_id,
            midday_summary.get("adjustments_made"),
            midday_summary.get("adjustments_helpful"),
            midday_summary.get("adjustments_harmful"),
            midday_summary.get("afternoon_accuracy"),
            midday_summary.get("key_adjustment"),
        )

    violations = data.get("mode_violations", [])
    if violations:
        await db.execute("DELETE FROM mode_violations WHERE record_id = $1", record_id)
        violation_rows = [(record_id, violation) for violation in violations]
        await db.execute_many(
            "INSERT INTO mode_violations (record_id, violation_text) VALUES ($1, $2)",
            violation_rows,
        )

    from ..insert_evaluations import insert_macro_evaluation, insert_rotation_evaluation

    rotation_eval = data.get("rotation_evaluation")
    if rotation_eval:
        await insert_rotation_evaluation(record_id, rotation_eval, db)

    macro_eval = data.get("macro_evaluation")
    if macro_eval:
        await insert_macro_evaluation(record_id, macro_eval, db)


async def insert_daily_record(scan_date: date, data: dict) -> bool:
    """Insert daily retrospective record with recommendations and evaluations."""
    db = await get_db()
    midday_data = data.get("midday_data") or {}
    trading_mode = _normalize_trading_mode(
        data.get("trading_mode") or midday_data.get("trading_mode")
    )
    mode_compliance = data.get("mode_compliance", True)

    # SWI-NN: hoist vn_universe ABOVE the txn so the txn block only holds DB work.
    try:
        vn_universe: frozenset[str] | None = await load_vn_universe_async()
    except VNUniverseUnavailable:
        vn_universe = None

    try:
        record_id = await _insert_recs_and_evals_atomic(
            db,
            scan_date,
            data,
            trading_mode,
            mode_compliance,
            vn_universe,
        )
        await _insert_ancillary_best_effort(db, record_id, data)
        return True
    except Exception as exc:
        narrow_db_error(exc, context=f"insert_daily_record scan_date={scan_date}")
        return False


insert_daily_record_sync = make_sync(insert_daily_record)
