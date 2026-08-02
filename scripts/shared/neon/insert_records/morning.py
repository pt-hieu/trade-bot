"""Morning brief recommendation insert + retrieval."""

from __future__ import annotations

import json
from datetime import date

from ...database import get_db
from ...vn_universe import VNUniverseUnavailable, load_vn_universe_async
from .._error_guard import narrow_db_error
from .._sync import make_sync
from .._utils import safe_float
from ._common import _INSERT_REC_SQL, _build_rec_row


async def insert_morning_recommendations(
    scan_date: date,
    market_regime: str | None,
    trading_mode: str | None,
    recommendations: list[dict],
    reflection_status: str | None = None,
    buy_signal_count: int | None = None,
    buy_rec_count: int | None = None,
    gate_decision_json: dict | None = None,
    global_risk_regime: str | None = None,
) -> bool:
    """Insert morning brief recommendations (no evaluations yet).

    Called right after synthesis. The retro will later upsert
    the same record with evaluations and summary stats.

    `global_risk_regime` is sourced from `gate_decision.inputs_digest`; the
    retro's `insert_daily_record` path re-writes it via COALESCE as a
    safety net for days where morning crashed before this insert.
    """
    db = await get_db()
    gate_payload = json.dumps(gate_decision_json) if gate_decision_json is not None else None

    # SWI-NN: hoist vn_universe ABOVE the transaction so the txn block only
    # contains DB-bound work (no awaits on unrelated I/O while the txn
    # connection is held).
    try:
        vn_universe: frozenset[str] | None = await load_vn_universe_async()
    except VNUniverseUnavailable:
        vn_universe = None

    try:
        # SWI-NN: parent UPSERT now inside the same transaction as the
        # child executemany. Critical implementation detail per `4cee2c2a`:
        # use `conn.fetchval/conn.execute/conn.executemany` — db.* methods
        # acquire NEW pool connections and bypass the transaction.
        async with db.transaction() as conn:
            record_id = await conn.fetchval(
                """
                INSERT INTO daily_records (
                    record_date, market_regime, trading_mode, reflection_status,
                    buy_signal_count, buy_rec_count, gate_decision_json,
                    global_risk_regime
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
                ON CONFLICT (record_date) DO UPDATE SET
                    market_regime = COALESCE(EXCLUDED.market_regime, daily_records.market_regime),
                    trading_mode = COALESCE(EXCLUDED.trading_mode, daily_records.trading_mode),
                    reflection_status = COALESCE(EXCLUDED.reflection_status, daily_records.reflection_status),
                    buy_signal_count = COALESCE(EXCLUDED.buy_signal_count, daily_records.buy_signal_count),
                    buy_rec_count = COALESCE(EXCLUDED.buy_rec_count, daily_records.buy_rec_count),
                    gate_decision_json = COALESCE(EXCLUDED.gate_decision_json, daily_records.gate_decision_json),
                    global_risk_regime = COALESCE(
                        EXCLUDED.global_risk_regime, daily_records.global_risk_regime
                    )
                RETURNING id
                """,
                scan_date,
                market_regime,
                trading_mode,
                reflection_status,
                buy_signal_count,
                buy_rec_count,
                gate_payload,
                global_risk_regime,
            )

            # Guard: if retro has already run (evaluations exist), don't clobber
            eval_count = await conn.fetchval(
                "SELECT COUNT(*) FROM daily_evaluations WHERE record_id = $1",
                record_id,
            )
            if eval_count and eval_count > 0:
                print(
                    f"  [Neon] Retro already ran for {scan_date} ({eval_count} evals), skipping morning re-insert"
                )
                return True

            rows = [
                row
                for rec in recommendations
                if (row := _build_rec_row(record_id, rec, vn_universe)) is not None
            ]

            # MORNING_EMPTY_RECS guard (`72ac5bf8`) — refuse to clobber
            # existing recs with an empty payload.
            if not rows:
                existing = await conn.fetchval(
                    "SELECT COUNT(*) FROM daily_recommendations WHERE record_id = $1",
                    record_id,
                )
                if existing and existing > 0:
                    raise RuntimeError(
                        f"MORNING_EMPTY_RECS scan_date={scan_date} "
                        f"existing_in_db={existing} incoming_rows=0 — refusing "
                        f"to DELETE existing recommendations."
                    )
            await conn.execute("DELETE FROM daily_recommendations WHERE record_id = $1", record_id)
            if rows:
                await conn.executemany(_INSERT_REC_SQL, rows)
        print(f"  [Neon] Inserted {len(rows)} morning recommendations for {scan_date}")
        return True
    except Exception as exc:
        narrow_db_error(exc, context=f"insert_morning_recommendations scan_date={scan_date}")
        return False


async def get_morning_recommendations(scan_date: date) -> list[dict]:
    """Get morning brief recommendations from database.

    Returns list of dicts matching parser agent output format:
    ticker, action, entry_price, stop_price, target_price, size_shares, rationale, section.
    Prices converted from BIGINT (VND x 1000) to float (VND).
    """
    db = await get_db()

    try:
        record = await db.fetch_one(
            "SELECT id FROM daily_records WHERE record_date = $1",
            scan_date,
        )
        if not record:
            print(f"  [Neon] No daily record found for {scan_date}")
            return []

        rows = await db.fetch_all(
            """
            SELECT ticker, action, entry_price_vnd, stop_price_vnd,
                   target_price_vnd, size_shares, rationale, section,
                   strategy, strategy_confidence,
                   risk_reward, verdict,
                   volume_vs_avg, volume_confirmed, pattern_name,
                   sim_ev, sim_p_target, sim_p_stop,
                   belief_conviction, source, urgency, counter_thesis,
                   plan_type
            FROM daily_recommendations
            WHERE record_id = $1
            ORDER BY section, ticker
            """,
            record["id"],
        )
        if not rows:
            print(f"  [Neon] No recommendations found for {scan_date}")
            return []

        recommendations = []
        for row in rows:
            recommendations.append(
                {
                    "ticker": row["ticker"],
                    "action": row["action"],
                    "entry_price": safe_float(row.get("entry_price_vnd")),
                    "stop_price": safe_float(row.get("stop_price_vnd")),
                    "target_price": safe_float(row.get("target_price_vnd")),
                    "size_shares": row.get("size_shares"),
                    "rationale": row.get("rationale"),
                    "section": row.get("section"),
                    "strategy": row.get("strategy"),
                    "strategy_confidence": row.get("strategy_confidence"),
                    "risk_reward": row.get("risk_reward"),
                    "verdict": row.get("verdict"),
                    "sim_ev": row.get("sim_ev"),
                    "sim_p_target": row.get("sim_p_target"),
                    "sim_p_stop": row.get("sim_p_stop"),
                    "source": row.get("source"),
                    "counter_thesis": row.get("counter_thesis"),
                    # Carried through so retro won-scoring resolves the correct
                    # ceiling + basis on dual-listed tickers.
                    "plan_type": row.get("plan_type"),
                }
            )

        print(f"  [Neon] Retrieved {len(recommendations)} recommendations from DB")
        return recommendations

    except Exception as exc:
        narrow_db_error(exc, context=f"get_morning_recommendations scan_date={scan_date}")
        return []


insert_morning_recommendations_sync = make_sync(insert_morning_recommendations)
get_morning_recommendations_sync = make_sync(get_morning_recommendations)
