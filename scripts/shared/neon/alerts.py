"""Alert system DB operations — register, query, trigger, expire."""

import json
import logging
from datetime import UTC, datetime

from ..database import get_db

logger = logging.getLogger(__name__)
from ._sync import make_sync

# Public API — lifecycle functions split to alert_lifecycle.py for 300-line rule
from .alert_lifecycle import (  # noqa: F401
    cancel_alerts_for_date,
    cancel_alerts_for_tickers,
    cancel_stale_alerts,
    cap_daily_alerts,
    cleanup_orphan_alerts,
)


async def register_alert(alert: dict) -> int:
    """Insert a compound alert with conditions, return alert ID.

    alert dict must include:
        ticker, source, source_date, conditions (list of {type, value})
    Optional:
        condition_logic (ALL/ANY), action_type, rationale,
        recommended_action, entry_price, stop_price, target_price,
        status, priority, expires_at, alert_metadata (JSONB dict or str)
    """
    db = await get_db()
    conditions = alert.get("conditions", [])
    # alert_metadata: accept dict or pre-serialized str
    raw_meta = alert.get("alert_metadata")
    alert_metadata = json.dumps(raw_meta) if isinstance(raw_meta, dict) else raw_meta
    try:
        alert_id = await db.fetch_val(
            """
            INSERT INTO alerts (
                ticker, condition_logic,
                action_type, source, source_date, rationale,
                recommended_action, entry_price, stop_price, target_price,
                status, priority, expires_at, alert_metadata
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb)
            ON CONFLICT (ticker, recommended_action, source_date, source)
                WHERE status = 'active'
                DO NOTHING
            RETURNING id
            """,
            alert["ticker"],
            alert.get("condition_logic", "ALL"),
            alert.get("action_type", "notify"),
            alert["source"],
            alert["source_date"],
            alert.get("rationale"),
            alert.get("recommended_action"),
            alert.get("entry_price"),
            alert.get("stop_price"),
            alert.get("target_price"),
            alert.get("status", "active"),
            alert.get("priority", "normal"),
            alert.get("expires_at"),
            alert_metadata,
        )

        # Duplicate alert — unique index prevented insert
        if alert_id is None:
            ticker = alert.get("ticker", "?")
            logger.info("Duplicate alert skipped for %s (already active)", ticker)
            return -1

        # Insert conditions
        for i, cond in enumerate(conditions):
            await db.execute(
                """INSERT INTO alert_conditions
                   (alert_id, condition_type, condition_value, params, sort_order)
                   VALUES ($1, $2, $3, $4::jsonb, $5)""",
                alert_id,
                cond["type"],
                cond.get("value"),
                json.dumps(cond.get("params", {})),
                i,
            )

        # Log creation event
        await db.execute(
            "INSERT INTO alert_history (alert_id, event_type) VALUES ($1, 'created')",
            alert_id,
        )
        return alert_id
    except Exception as e:
        logger.error("Failed to register alert: %s", e)
        return -1


async def register_alerts_batch(alerts: list[dict]) -> int:
    """Insert multiple compound alerts. Returns count of successfully inserted."""
    count = 0
    for alert in alerts:
        aid = await register_alert(alert)
        if aid > 0:
            count += 1
    return count


async def get_active_alerts() -> list[dict]:
    """Get all active alerts with their conditions."""
    db = await get_db()
    alerts = await db.fetch_all(
        "SELECT * FROM alerts WHERE status = 'active' ORDER BY priority DESC, created_at"
    )
    if not alerts:
        return []

    alert_list = [dict(a) for a in alerts]
    alert_ids = [a["id"] for a in alert_list]

    # Fetch all conditions in one query
    placeholders = ", ".join(f"${i + 1}" for i in range(len(alert_ids)))
    conditions = await db.fetch_all(
        f"""SELECT * FROM alert_conditions
            WHERE alert_id IN ({placeholders})
            ORDER BY alert_id, sort_order""",
        *alert_ids,
    )

    # Group conditions by alert_id
    cond_by_alert: dict[int, list[dict]] = {}
    for c in conditions:
        c_dict = dict(c)
        aid = c_dict["alert_id"]
        cond_by_alert.setdefault(aid, []).append(c_dict)

    # Merge conditions into alerts
    for a in alert_list:
        a["conditions"] = cond_by_alert.get(a["id"], [])

    return alert_list


async def trigger_alert(alert_id: int, triggered_values: dict) -> None:
    """Mark an alert as triggered with compound triggered values."""
    db = await get_db()
    now = datetime.now(UTC)
    await db.execute(
        """UPDATE alerts SET status = 'triggered', triggered_at = $1,
           triggered_values = $2::jsonb, updated_at = $1 WHERE id = $3""",
        now,
        json.dumps(triggered_values),
        alert_id,
    )
    await db.execute(
        """INSERT INTO alert_history (alert_id, event_type, event_data)
           VALUES ($1, 'triggered', $2::jsonb)""",
        alert_id,
        json.dumps(triggered_values),
    )


async def expire_stale_alerts() -> int:
    """Expire alerts past their expires_at. Returns count expired."""
    db = await get_db()
    now = datetime.now(UTC)
    result = await db.execute(
        "UPDATE alerts SET status = 'expired', updated_at = $1 WHERE status = 'active' AND expires_at < $1",
        now,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


async def get_alerts_for_web(
    status: str | None = None, ticker: str | None = None, limit: int = 100
) -> list[dict]:
    """Get alerts with conditions for web display."""
    db = await get_db()
    conditions_sql = []
    params: list = []
    idx = 1

    if status:
        conditions_sql.append(f"a.status = ${idx}")
        params.append(status)
        idx += 1
    if ticker:
        conditions_sql.append(f"a.ticker = ${idx}")
        params.append(ticker.upper())
        idx += 1

    where = "WHERE " + " AND ".join(conditions_sql) if conditions_sql else ""
    params.append(limit)

    alerts = await db.fetch_all(
        f"""SELECT * FROM alerts a {where}
            ORDER BY a.created_at DESC LIMIT ${idx}""",
        *params,
    )
    if not alerts:
        return []

    alert_list = [dict(a) for a in alerts]
    alert_ids = [a["id"] for a in alert_list]

    placeholders = ", ".join(f"${i + 1}" for i in range(len(alert_ids)))
    cond_rows = await db.fetch_all(
        f"""SELECT * FROM alert_conditions
            WHERE alert_id IN ({placeholders})
            ORDER BY alert_id, sort_order""",
        *alert_ids,
    )

    cond_by_alert: dict[int, list[dict]] = {}
    for c in cond_rows:
        c_dict = dict(c)
        aid = c_dict["alert_id"]
        cond_by_alert.setdefault(aid, []).append(c_dict)

    for a in alert_list:
        a["conditions"] = cond_by_alert.get(a["id"], [])

    return alert_list


async def get_recent_trigger_times(alert_ids: list[int]) -> dict[int, datetime]:
    """Get most recent trigger time for given alert IDs (for dedup)."""
    if not alert_ids:
        return {}
    db = await get_db()
    placeholders = ", ".join(f"${i + 1}" for i in range(len(alert_ids)))
    rows = await db.fetch_all(
        f"""SELECT alert_id, MAX(created_at) as last_trigger
            FROM alert_history
            WHERE alert_id IN ({placeholders}) AND event_type = 'triggered'
            GROUP BY alert_id""",
        *alert_ids,
    )
    return {r["alert_id"]: r["last_trigger"] for r in rows}


# Sync wrappers
register_alert_sync = make_sync(register_alert)
get_active_alerts_sync = make_sync(get_active_alerts)
expire_stale_alerts_sync = make_sync(expire_stale_alerts)
cancel_alerts_for_date_sync = make_sync(cancel_alerts_for_date)
get_alerts_for_web_sync = make_sync(get_alerts_for_web)
