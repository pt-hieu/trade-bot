"""Batch-fetch functions for learnings reconstruction.

Each function takes a DB handle and list of record_ids, returns
results grouped by record_id for O(1) lookup in the assembly loop.
"""

from collections import defaultdict
from typing import Any


def _group_by(rows: list[dict[str, Any]], key: str) -> dict[int, list[dict[str, Any]]]:
    """Group rows by a column value into a dict of lists."""
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row[key]].append(row)
    return grouped


async def batch_fetch_evaluations(
    db: Any, record_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Fetch daily_evaluations LEFT JOIN daily_recommendations for all record_ids."""
    rows = await db.fetch_all(
        """
        SELECT de.record_id,
               de.ticker, de.recommendation::text AS recommendation, de.section,
               de.entry_hit, de.stop_hit, de.target_hit, de.eod_price_vnd,
               de.pnl_percent, de.status::text AS status, de.analysis, de.won,
               de.entry_gap_pct, de.predicted_rr, de.actual_max_rr,
               de.stop_buffer_pct, de.stop_vs_atr_ratio, de.atr_pct,
               de.day_change, de.trade_executed, de.actual_pl_pct,
               de.actual_exit_price_vnd, de.actual_pl_net_vnd,
               COALESCE(de.strategy, dr.strategy) AS strategy
        FROM daily_evaluations de
        LEFT JOIN daily_recommendations dr
          ON dr.record_id = de.record_id AND dr.ticker = de.ticker
        WHERE de.record_id = ANY($1)
        """,
        record_ids,
    )
    return _group_by([dict(r) for r in rows], "record_id")


async def batch_fetch_recommendations(
    db: Any, record_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Fetch daily_recommendations for all record_ids."""
    rows = await db.fetch_all(
        """
        SELECT record_id, ticker, action::text AS action, entry_price_vnd,
               stop_price_vnd, target_price_vnd, size_shares, rationale, section
        FROM daily_recommendations WHERE record_id = ANY($1)
        """,
        record_ids,
    )
    return _group_by([dict(r) for r in rows], "record_id")


async def batch_fetch_violations(db: Any, record_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Fetch mode_violations for all record_ids."""
    rows = await db.fetch_all(
        "SELECT record_id, violation_text FROM mode_violations WHERE record_id = ANY($1)",
        record_ids,
    )
    return _group_by([dict(r) for r in rows], "record_id")


async def batch_fetch_midday(db: Any, record_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Fetch midday_data for all record_ids. Returns first row per record_id.

    ``afternoon_plan`` is JSONB (migration 316); asyncpg surfaces it as a raw
    string, so parse it here so downstream learnings + retro paths see the
    structured list they expect.
    """
    from shared.neon._utils import parse_jsonb_list

    rows = await db.fetch_all(
        """
        SELECT record_id, trading_mode::text AS trading_mode, entries_hit, afternoon_plan
        FROM midday_data WHERE record_id = ANY($1)
        """,
        record_ids,
    )
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        record_id = row["record_id"]
        if record_id not in result:
            parsed = dict(row)
            parsed["afternoon_plan"] = parse_jsonb_list(parsed.get("afternoon_plan"))
            result[record_id] = parsed
    return result


async def batch_fetch_midday_summaries(db: Any, record_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Fetch midday_summaries for all record_ids. Returns first row per record_id."""
    rows = await db.fetch_all(
        """
        SELECT record_id, adjustments_made, adjustments_helpful, adjustments_harmful,
               afternoon_accuracy, key_adjustment
        FROM midday_summaries WHERE record_id = ANY($1)
        """,
        record_ids,
    )
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        record_id = row["record_id"]
        if record_id not in result:
            result[record_id] = dict(row)
    return result


async def batch_fetch_rotation_evals(db: Any, record_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Fetch rotation_evaluations + sector_returns for all record_ids.

    Uses a single JOIN for sector_returns through rotation_evaluations,
    avoiding the two-step fetch pattern.
    """
    # Fetch rotation evaluations
    rotation_rows = await db.fetch_all(
        """SELECT id, record_id, market_regime::text AS market_regime,
                  hot_avg_return, cold_avg_return, market_avg_return,
                  hot_vs_market, cold_vs_market,
                  hot_hit_rate, cold_hit_rate, overall_accuracy,
                  rotation_effective, hot_sectors, cold_sectors
           FROM rotation_evaluations WHERE record_id = ANY($1)""",
        record_ids,
    )
    if not rotation_rows:
        return {}

    # Map rotation_eval_id → record_id for sector returns lookup
    eval_id_to_record_id: dict[int, int] = {}
    rotation_by_record: dict[int, dict[str, Any]] = {}
    for row in rotation_rows:
        record_id = row["record_id"]
        eval_id_to_record_id[row["id"]] = record_id
        hot_sectors = row["hot_sectors"] or []
        cold_sectors = row["cold_sectors"] or []
        rotation_by_record[record_id] = {
            "hot_sectors": hot_sectors if isinstance(hot_sectors, list) else [],
            "cold_sectors": cold_sectors if isinstance(cold_sectors, list) else [],
            "market_regime": row["market_regime"],
            "sector_returns": {},
            "hot_avg_return": float(row["hot_avg_return"] or 0),
            "cold_avg_return": float(row["cold_avg_return"] or 0),
            "market_avg_return": float(row["market_avg_return"] or 0),
            "hot_vs_market": float(row["hot_vs_market"] or 0),
            "cold_vs_market": float(row["cold_vs_market"] or 0),
            "hot_hit_rate": float(row["hot_hit_rate"] or 0),
            "cold_hit_rate": float(row["cold_hit_rate"] or 0),
            "overall_accuracy": float(row["overall_accuracy"] or 0),
            "rotation_effective": row["rotation_effective"] or False,
        }

    # Batch-fetch sector returns via JOIN
    sector_rows = await db.fetch_all(
        """SELECT re.record_id, s.name AS sector_name, rsr.return_pct
           FROM rotation_sector_returns rsr
           JOIN rotation_evaluations re ON rsr.rotation_eval_id = re.id
           JOIN sectors s ON rsr.sector_id = s.id
           WHERE re.record_id = ANY($1)""",
        record_ids,
    )
    for sector_row in sector_rows:
        record_id = sector_row["record_id"]
        if record_id in rotation_by_record:
            rotation_by_record[record_id]["sector_returns"][sector_row["sector_name"]] = float(
                sector_row["return_pct"]
            )

    return rotation_by_record


async def batch_fetch_macro_evals(db: Any, record_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Fetch macro_evaluations for all record_ids. Returns first row per record_id."""
    rows = await db.fetch_all(
        """SELECT record_id, global_risk_regime::text AS global_risk_regime,
                  dxy_value, vix_value, vn_index_change_pct,
                  regime_appropriate, foreign_flow_aligned, recommendation_compliance
           FROM macro_evaluations WHERE record_id = ANY($1)""",
        record_ids,
    )
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        record_id = row["record_id"]
        if record_id not in result:
            result[record_id] = {
                "global_risk_regime": row["global_risk_regime"],
                "dxy_value": float(row["dxy_value"]) if row["dxy_value"] is not None else None,
                "vix_value": float(row["vix_value"]) if row["vix_value"] is not None else None,
                "vn_index_change_pct": float(row["vn_index_change_pct"])
                if row["vn_index_change_pct"] is not None
                else None,
                "regime_appropriate": row["regime_appropriate"],
                "foreign_flow_aligned": row["foreign_flow_aligned"],
                "recommendation_compliance": row["recommendation_compliance"],
            }
    return result
