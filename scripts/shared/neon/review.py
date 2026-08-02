"""Read-only queries for pipeline review data collection.

These wrap queries from .claude/skills/pipeline-review/references/queries.md
that don't have existing shared/neon/ functions.
"""

from datetime import date

from ..database import get_db


async def get_daily_evaluations(scan_date: date) -> list[dict]:
    """Fetch retro evaluations for a given date."""
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT ticker, recommendation, entry_hit, stop_hit, target_hit,
               eod_price_vnd, pnl_percent, status, won, analysis, section,
               plan_type, rule_applied
        FROM daily_evaluations
        WHERE record_id = (
            SELECT id FROM daily_records WHERE record_date = $1
        )
        """,
        scan_date,
    )
    return [dict(row) for row in rows]


async def get_beliefs_for_date(scan_date: date) -> list[dict]:
    """Fetch all agent beliefs recorded on a specific date."""
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT id, record_date, ticker, agent_key, ensemble_type, direction,
               bull_probability, base_probability, bear_probability,
               price_target_vnd, timeframe_days, conviction, belief_status,
               prior_belief_id, days_held, update_reason
        FROM agent_beliefs
        WHERE record_date = $1
        ORDER BY ensemble_type, ticker, agent_key
        """,
        scan_date,
    )
    return [dict(row) for row in rows]


async def get_orphaned_belief_chains(scan_date: date) -> list[dict]:
    """Find beliefs where prior_belief_id points to a non-existent row.

    Looks back 7 days from scan_date for broken chain links.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT ab.id, ab.ticker, ab.agent_key, ab.prior_belief_id
        FROM agent_beliefs ab
        LEFT JOIN agent_beliefs prior ON ab.prior_belief_id = prior.id
        WHERE ab.prior_belief_id IS NOT NULL
          AND prior.id IS NULL
          AND ab.record_date >= $1::date - 7
        """,
        scan_date,
    )
    return [dict(row) for row in rows]


async def get_alerts_by_source_date(scan_date: date) -> list[dict]:
    """Fetch alerts and their conditions for a specific source date."""
    db = await get_db()
    alerts = await db.fetch_all(
        """
        SELECT id, ticker, action_type, status, condition_logic,
               source_date, rationale, entry_price, stop_price, target_price
        FROM alerts
        WHERE source_date = $1
        ORDER BY ticker
        """,
        scan_date,
    )
    if not alerts:
        return []

    alert_list = [dict(a) for a in alerts]
    alert_ids = [a["id"] for a in alert_list]

    placeholders = ", ".join(f"${i + 1}" for i in range(len(alert_ids)))
    conditions = await db.fetch_all(
        f"""SELECT alert_id, condition_type, condition_value, sort_order
            FROM alert_conditions
            WHERE alert_id IN ({placeholders})
            ORDER BY alert_id, sort_order""",
        *alert_ids,
    )

    conditions_by_alert: dict[int, list[dict]] = {}
    for condition in conditions:
        condition_dict = dict(condition)
        alert_id = condition_dict["alert_id"]
        conditions_by_alert.setdefault(alert_id, []).append(condition_dict)

    for alert in alert_list:
        alert["conditions"] = conditions_by_alert.get(alert["id"], [])

    return alert_list
