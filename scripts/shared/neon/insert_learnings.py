"""Insert function for learnings data (full replacement)."""

import json as json_mod
from datetime import datetime

from ..database import get_db
from ._sync import make_sync


def normalize_rate(value: float | None) -> float | None:
    """Normalize rate to 0-1 scale. LLMs sometimes return 0-100 scale."""
    if value is not None and value > 1.0:
        return value / 100.0
    return value


async def insert_learnings(data: dict) -> bool:
    """Insert/update learnings data (full replacement)."""
    db = await get_db()

    try:
        # 1. Update summary
        last_updated = data.get("last_updated")
        if last_updated:
            last_updated = datetime.strptime(last_updated, "%Y-%m-%d").date()

        rolling_window = data.get("rolling_window_days", 7)
        summary = data.get("summary", {})

        total_days = summary.get("total_days") or 0
        if total_days == 0:
            print("  [Learnings] Skipping summary update — total_days=0 (preserving existing)")
        else:
            await db.execute("DELETE FROM learnings_summary")
            await db.execute(
                """
                INSERT INTO learnings_summary (
                    last_updated, rolling_window_days, total_days, total_recs,
                    overall_entry_hit_rate, overall_win_rate, avg_pnl_percent,
                    swing_win_rate, longterm_win_rate, swing_sample_size
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                last_updated,
                rolling_window,
                summary.get("total_days"),
                summary.get("total_recs"),
                summary.get("overall_entry_hit_rate"),
                summary.get("overall_win_rate"),
                summary.get("avg_pnl_percent"),
                summary.get("swing_win_rate"),
                summary.get("longterm_win_rate"),
                summary.get("swing_sample_size"),
            )

        # 2. Update patterns — only replace if new patterns exist
        # NEVER wipe historical patterns when retro produces 0 (due to min sample size)
        new_winning = data.get("winning_patterns", [])
        new_losing = data.get("losing_patterns", [])
        if new_winning or new_losing:
            await db.execute("DELETE FROM learning_patterns")
        else:
            print("  [Learnings] No new patterns — preserving existing rows (0 produced by retro)")

        for pattern_type, patterns in [("winning", new_winning), ("losing", new_losing)]:
            for pattern in patterns or []:
                await db.execute(
                    """
                    INSERT INTO learning_patterns (
                        pattern_type, pattern_description, win_rate, loss_rate,
                        sample_size, actionable_rule, avoid_rule, dominant_error
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    pattern_type,
                    pattern.get("pattern"),
                    pattern.get("win_rate"),
                    pattern.get("loss_rate"),
                    pattern.get("sample_size"),
                    pattern.get("actionable_rule"),
                    pattern.get("avoid_rule"),
                    pattern.get("dominant_error"),
                )

        # 3. Update sector insights
        new_insights = data.get("sector_insights", [])
        if not new_insights:
            print("  [Learnings] No sector insights — preserving existing rows")
        else:
            await db.execute("DELETE FROM sector_insights")

        for insight in new_insights:
            sector_name = insight.get("sector", "").lower().replace(" ", "_").replace("-", "_")
            sector_id = await db.fetch_val("SELECT id FROM sectors WHERE name = $1", sector_name)

            if not sector_id:
                sector_map = {
                    "state_owned": "state_owned",
                    "banking": "banking",
                    "technology": "technology",
                    "real_estate": "real_estate",
                    "infrastructure": "infrastructure",
                    "consumer": "consumer",
                }
                sector_id = await db.fetch_val(
                    "SELECT id FROM sectors WHERE name = $1",
                    sector_map.get(sector_name, "infrastructure"),
                )

            if sector_id:
                bias = insight.get("bias")
                if bias in ("Strong/Resilient", "bullish"):
                    bias = "hot"
                elif bias in ("Weak/Choppy", "bearish"):
                    bias = "cold"
                elif bias in ("Mixed", "neutral"):
                    bias = "neutral"

                # Normalize to 0-1 scale (LLMs sometimes return 0-100)
                win_rate = normalize_rate(insight.get("win_rate"))

                await db.execute(
                    """
                    INSERT INTO sector_insights (sector_id, bias, win_rate)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (sector_id) DO UPDATE SET
                        bias = EXCLUDED.bias, win_rate = EXCLUDED.win_rate, updated_at = NOW()
                    """,
                    sector_id,
                    bias,
                    win_rate,
                )

        # 4. Update ticker insights
        new_ticker_insights = data.get("ticker_insights", [])
        if not new_ticker_insights:
            print("  [Learnings] No ticker insights — preserving existing rows")
        else:
            await db.execute("DELETE FROM ticker_insights")

        for insight in new_ticker_insights:
            ticker = insight.get("ticker")
            if ticker:
                # Normalize to 0-1 scale (LLMs sometimes return 0-100)
                accuracy = insight.get("recent_accuracy")
                if accuracy is not None and accuracy > 1.0:
                    accuracy = accuracy / 100.0

                await db.execute(
                    """
                    INSERT INTO ticker_insights (ticker, recent_accuracy)
                    VALUES ($1, $2)
                    ON CONFLICT (ticker) DO UPDATE SET recent_accuracy = EXCLUDED.recent_accuracy, updated_at = NOW()
                    """,
                    ticker,
                    accuracy,
                )

        # 5. Update midday patterns
        midday_patterns = data.get("midday_patterns", {})
        if midday_patterns:
            await db.execute("DELETE FROM midday_patterns")
            await db.execute(
                """
                INSERT INTO midday_patterns (
                    days_with_midday, adjustment_win_rate, when_helpful, when_harmful, average_improvement
                ) VALUES ($1, $2, $3, $4, $5)
                """,
                midday_patterns.get("days_with_midday"),
                midday_patterns.get("adjustment_win_rate"),
                json_mod.dumps(midday_patterns.get("when_helpful", [])),
                json_mod.dumps(midday_patterns.get("when_harmful", [])),
                midday_patterns.get("average_improvement"),
            )

        # 6. Update trading mode patterns
        trading_mode_patterns = data.get("trading_mode_patterns", {})
        if trading_mode_patterns:
            await db.execute("DELETE FROM trading_mode_patterns")
            await db.execute(
                """
                INSERT INTO trading_mode_patterns (
                    mode_compliance_rate, mode_violations, mode_appropriate_win_rate
                ) VALUES ($1, $2, $3)
                """,
                trading_mode_patterns.get("mode_compliance_rate"),
                json_mod.dumps(trading_mode_patterns.get("mode_violations", [])),
                trading_mode_patterns.get("mode_appropriate_win_rate"),
            )

        # 7. Update rotation patterns
        rotation_patterns = data.get("rotation_patterns", {})
        if rotation_patterns:
            await db.execute("DELETE FROM rotation_sector_scores")
            await db.execute("DELETE FROM rotation_patterns")

            pattern_id = await db.fetch_val(
                """
                INSERT INTO rotation_patterns (
                    total_days, overall_accuracy, hot_hit_rate, cold_hit_rate,
                    avg_hot_vs_market, avg_cold_vs_market
                ) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
                """,
                rotation_patterns.get("total_days"),
                rotation_patterns.get("overall_accuracy"),
                rotation_patterns.get("hot_hit_rate"),
                rotation_patterns.get("cold_hit_rate"),
                rotation_patterns.get("avg_hot_vs_market"),
                rotation_patterns.get("avg_cold_vs_market"),
            )

            for sector_name, scores in rotation_patterns.get("sector_rotation_score", {}).items():
                sector_key = sector_name.lower().replace(" ", "_").replace("-", "_")
                sector_id = await db.fetch_val("SELECT id FROM sectors WHERE name = $1", sector_key)
                if sector_id:
                    await db.execute(
                        "INSERT INTO rotation_sector_scores (pattern_id, sector_id, as_hot_accuracy, as_cold_accuracy) VALUES ($1, $2, $3, $4)",
                        pattern_id,
                        sector_id,
                        scores.get("as_hot"),
                        scores.get("as_cold"),
                    )

        # 8. Update macro patterns
        macro_patterns = data.get("macro_patterns", {})
        if macro_patterns and macro_patterns.get("total_days", 0) > 0:
            await db.execute("DELETE FROM macro_regime_accuracy")
            await db.execute("DELETE FROM macro_patterns")

            pattern_id = await db.fetch_val(
                """
                INSERT INTO macro_patterns (
                    total_days, overall_accuracy, false_alarms, missed_drops, missed_opportunities
                ) VALUES ($1, $2, $3, $4, $5) RETURNING id
                """,
                macro_patterns.get("total_days"),
                macro_patterns.get("overall_accuracy"),
                macro_patterns.get("false_alarms"),
                macro_patterns.get("missed_drops"),
                macro_patterns.get("missed_opportunities") or 0,
            )

            for regime, accuracy in macro_patterns.get("regime_accuracy", {}).items():
                await db.execute(
                    "INSERT INTO macro_regime_accuracy (pattern_id, regime, days_count, correct_count, avg_vn_change) VALUES ($1, $2, $3, $4, $5)",
                    pattern_id,
                    regime,
                    accuracy.get("days"),
                    accuracy.get("correct"),
                    accuracy.get("avg_vn_change"),
                )

        # 9. Update calibration insights
        calibration = data.get("calibration_insights", {})
        if calibration and calibration.get("sample_size", 0) > 0:
            last_trade_exit_date_raw = calibration.get("last_trade_exit_date") or None
            last_trade_exit_date = (
                datetime.strptime(last_trade_exit_date_raw, "%Y-%m-%d").date()
                if isinstance(last_trade_exit_date_raw, str)
                else last_trade_exit_date_raw
            )
            await db.execute(
                """
                INSERT INTO calibration_insights (
                    scan_date, avg_entry_gap_pct, pct_entries_unreachable,
                    avg_stop_vs_atr, pct_stops_too_tight,
                    avg_predicted_rr, avg_actual_rr, target_hit_rate, sample_size,
                    last_trade_exit_date, swing_sample_size
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (scan_date) DO UPDATE SET
                    avg_entry_gap_pct = EXCLUDED.avg_entry_gap_pct,
                    pct_entries_unreachable = EXCLUDED.pct_entries_unreachable,
                    avg_stop_vs_atr = EXCLUDED.avg_stop_vs_atr,
                    pct_stops_too_tight = EXCLUDED.pct_stops_too_tight,
                    avg_predicted_rr = EXCLUDED.avg_predicted_rr,
                    avg_actual_rr = EXCLUDED.avg_actual_rr,
                    target_hit_rate = EXCLUDED.target_hit_rate,
                    sample_size = EXCLUDED.sample_size,
                    last_trade_exit_date = EXCLUDED.last_trade_exit_date,
                    swing_sample_size = EXCLUDED.swing_sample_size
                """,
                last_updated,
                calibration.get("avg_entry_gap_pct"),
                calibration.get("pct_entries_unreachable"),
                calibration.get("avg_stop_vs_atr"),
                calibration.get("pct_stops_too_tight"),
                calibration.get("avg_predicted_rr"),
                calibration.get("avg_actual_rr"),
                calibration.get("target_hit_rate"),
                calibration.get("sample_size"),
                last_trade_exit_date,
                calibration.get("swing_sample_size") or None,
            )

        return True
    except Exception as e:
        print(f"  [Neon] Failed to insert learnings: {e}")
        return False


# ============================================================================
# Sync Wrappers
# ============================================================================

insert_learnings_sync = make_sync(insert_learnings)
