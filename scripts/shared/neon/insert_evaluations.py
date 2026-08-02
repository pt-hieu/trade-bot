"""Insert functions for rotation and macro evaluation child records."""

import json
import logging

logger = logging.getLogger(__name__)


async def insert_rotation_evaluation(record_id, rotation_eval: dict, db) -> bool:
    """Persist rotation evaluation and per-sector returns for a daily record.

    Uses ON CONFLICT (record_id) DO UPDATE for idempotent re-runs.
    """
    try:
        market_regime = rotation_eval.get("market_regime")
        # Normalize market_regime to valid enum or None
        valid_regimes = {"NEUTRAL", "RISK_ON", "RISK_OFF"}
        if market_regime and market_regime.upper() not in valid_regimes:
            market_regime = None
        elif market_regime:
            market_regime = market_regime.upper()

        eval_id = await db.fetch_val(
            """
            INSERT INTO rotation_evaluations (
                record_id, market_regime, hot_avg_return, cold_avg_return,
                market_avg_return, hot_vs_market, cold_vs_market,
                hot_hit_rate, cold_hit_rate, overall_accuracy,
                rotation_effective, hot_sectors, cold_sectors
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb)
            ON CONFLICT (record_id) DO UPDATE SET
                market_regime = EXCLUDED.market_regime,
                hot_avg_return = EXCLUDED.hot_avg_return,
                cold_avg_return = EXCLUDED.cold_avg_return,
                market_avg_return = EXCLUDED.market_avg_return,
                hot_vs_market = EXCLUDED.hot_vs_market,
                cold_vs_market = EXCLUDED.cold_vs_market,
                hot_hit_rate = EXCLUDED.hot_hit_rate,
                cold_hit_rate = EXCLUDED.cold_hit_rate,
                overall_accuracy = EXCLUDED.overall_accuracy,
                rotation_effective = EXCLUDED.rotation_effective,
                hot_sectors = EXCLUDED.hot_sectors,
                cold_sectors = EXCLUDED.cold_sectors
            RETURNING id
            """,
            record_id,
            market_regime,
            rotation_eval.get("hot_avg_return"),
            rotation_eval.get("cold_avg_return"),
            rotation_eval.get("market_avg_return"),
            rotation_eval.get("hot_vs_market"),
            rotation_eval.get("cold_vs_market"),
            rotation_eval.get("hot_hit_rate"),
            rotation_eval.get("cold_hit_rate"),
            rotation_eval.get("overall_accuracy"),
            rotation_eval.get("rotation_effective") or False,
            json.dumps(rotation_eval.get("hot_sectors") or []),
            json.dumps(rotation_eval.get("cold_sectors") or []),
        )

        # Persist per-sector returns
        sector_returns = rotation_eval.get("sector_returns") or {}
        if sector_returns and eval_id:
            await db.execute(
                "DELETE FROM rotation_sector_returns WHERE rotation_eval_id = $1",
                eval_id,
            )
            all_sectors = await db.fetch_all("SELECT id, name FROM sectors")
            sector_map = {row["name"]: row["id"] for row in all_sectors}

            insert_args = []
            for sector_name, return_pct in sector_returns.items():
                sector_key = sector_name.lower().replace(" ", "_").replace("-", "_")
                sector_id = sector_map.get(sector_key)
                if sector_id:
                    insert_args.append((eval_id, sector_id, return_pct))

            if insert_args:
                await db.execute_many(
                    """INSERT INTO rotation_sector_returns
                       (rotation_eval_id, sector_id, return_pct)
                       VALUES ($1, $2, $3)""",
                    insert_args,
                )

        return True
    except Exception as error:
        logger.warning("Failed to insert rotation evaluation: %s", error)
        return False


async def insert_macro_evaluation(record_id, macro_eval: dict, db) -> bool:
    """Persist macro regime evaluation for a daily record.

    Uses ON CONFLICT (record_id) DO UPDATE for idempotent re-runs.
    """
    try:
        recommendation_compliance = macro_eval.get("recommendation_compliance")
        # Column is BOOLEAN — cast float to bool if needed
        if isinstance(recommendation_compliance, (int, float)):
            recommendation_compliance = bool(recommendation_compliance >= 0.5)

        await db.execute(
            """
            INSERT INTO macro_evaluations (
                record_id, global_risk_regime, dxy_value, vix_value,
                vn_index_change_pct, regime_appropriate,
                foreign_flow_aligned, recommendation_compliance
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (record_id) DO UPDATE SET
                global_risk_regime = EXCLUDED.global_risk_regime,
                dxy_value = EXCLUDED.dxy_value,
                vix_value = EXCLUDED.vix_value,
                vn_index_change_pct = EXCLUDED.vn_index_change_pct,
                regime_appropriate = EXCLUDED.regime_appropriate,
                foreign_flow_aligned = EXCLUDED.foreign_flow_aligned,
                recommendation_compliance = EXCLUDED.recommendation_compliance
            """,
            record_id,
            macro_eval.get("global_risk_regime"),
            macro_eval.get("dxy_value"),
            macro_eval.get("vix_value"),
            macro_eval.get("vn_index_change_pct"),
            macro_eval.get("regime_appropriate"),
            macro_eval.get("foreign_flow_aligned"),
            recommendation_compliance,
        )
        return True
    except Exception as error:
        logger.warning("Failed to insert macro evaluation: %s", error)
        return False
