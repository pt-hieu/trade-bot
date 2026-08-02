"""Learnings, patterns, and trading insights queries."""

import logging
from datetime import date, timedelta
from typing import Any, TypedDict

from ..database import get_db
from ._sync import make_sync
from ._utils import safe_float


class CalibrationInsightsRow(TypedDict, total=False):
    """Calibration insights row enriched with derived staleness_days."""

    avg_entry_gap_pct: float | None
    pct_entries_unreachable: float | None
    avg_stop_vs_atr: float | None
    pct_stops_too_tight: float | None
    avg_predicted_rr: float | None
    avg_actual_rr: float | None
    target_hit_rate: float | None
    sample_size: int | None
    swing_sample_size: int | None
    last_trade_exit_date: str | None
    staleness_days: int | None
    as_of: str


logger = logging.getLogger(__name__)

_STALE_DAYS = 7


def _check_staleness(updated_at, label: str) -> bool:
    """Log warning if data is stale. Returns True if stale."""
    if updated_at is None:
        return False
    cutoff = date.today() - timedelta(days=_STALE_DAYS)
    dt = updated_at.date() if hasattr(updated_at, "date") else updated_at
    if dt < cutoff:
        logger.warning("%s data is %d days old (updated %s)", label, (date.today() - dt).days, dt)
        return True
    return False


async def get_learnings_summary() -> dict:
    """Get learnings summary stats."""
    db = await get_db()
    row = await db.fetch_one("""
        SELECT total_days, total_recs, overall_entry_hit_rate, overall_win_rate,
               avg_pnl_percent, rolling_window_days, updated_at,
               swing_win_rate, longterm_win_rate, swing_sample_size
        FROM learnings_summary ORDER BY updated_at DESC LIMIT 1
    """)

    if not row:
        return {}

    _check_staleness(row.get("updated_at"), "learnings_summary")
    return {
        "total_days": row["total_days"],
        "total_recs": row["total_recs"],
        "overall_entry_hit_rate": safe_float(row["overall_entry_hit_rate"], default=0),
        "overall_win_rate": safe_float(row["overall_win_rate"], default=0),
        "avg_pnl_percent": safe_float(row["avg_pnl_percent"], default=0),
        "rolling_window_days": row["rolling_window_days"],
        "swing_win_rate": safe_float(row.get("swing_win_rate")),
        "longterm_win_rate": safe_float(row.get("longterm_win_rate")),
        "swing_sample_size": row.get("swing_sample_size"),
    }


async def get_winning_patterns(
    sector: str | None = None, action: str | None = None, limit: int = 5
) -> list[dict]:
    """Get winning patterns with optional filters."""
    db = await get_db()

    query = """
        SELECT pattern_description, win_rate, sample_size, actionable_rule
        FROM learning_patterns WHERE pattern_type = 'winning'
    """
    params: list[Any] = []

    if sector:
        params.append(f"%{sector.lower()}%")
        query += f" AND LOWER(pattern_description) LIKE ${len(params)}"
    if action:
        params.append(f"%{action.upper()}%")
        query += f" AND UPPER(pattern_description) LIKE ${len(params)}"

    params.append(limit)
    query += f" ORDER BY win_rate DESC, sample_size DESC LIMIT ${len(params)}"

    rows = await db.fetch_all(query, *params)

    return [
        {
            "pattern": row["pattern_description"],
            "win_rate": safe_float(row["win_rate"], default=0),
            "sample_size": row["sample_size"],
            "rule": row["actionable_rule"],
        }
        for row in rows
    ]


async def get_losing_patterns(action: str | None = None, limit: int = 5) -> list[dict]:
    """Get losing patterns with optional filters."""
    db = await get_db()

    query = """
        SELECT pattern_description, loss_rate, sample_size, avoid_rule
        FROM learning_patterns WHERE pattern_type = 'losing'
    """
    params: list[Any] = []

    if action:
        params.append(f"%{action.upper()}%")
        query += f" AND UPPER(pattern_description) LIKE ${len(params)}"

    params.append(limit)
    query += f" ORDER BY loss_rate DESC, sample_size DESC LIMIT ${len(params)}"

    rows = await db.fetch_all(query, *params)

    return [
        {
            "pattern": row["pattern_description"],
            "loss_rate": safe_float(row["loss_rate"], default=0),
            "sample_size": row["sample_size"],
            "avoid": row["avoid_rule"],
        }
        for row in rows
    ]


async def get_sector_insights(sector: str | None = None) -> list[dict]:
    """Get sector insights."""
    db = await get_db()

    if sector:
        rows = await db.fetch_all(
            """
            SELECT s.name as sector, si.bias, si.win_rate as recent_accuracy
            FROM sector_insights si JOIN sectors s ON s.id = si.sector_id
            WHERE LOWER(s.name) LIKE $1 ORDER BY si.win_rate DESC
        """,
            f"%{sector.lower()}%",
        )
    else:
        rows = await db.fetch_all("""
            SELECT s.name as sector, si.bias, si.win_rate as recent_accuracy
            FROM sector_insights si JOIN sectors s ON s.id = si.sector_id
            ORDER BY si.win_rate DESC
        """)

    return [
        {
            "sector": row["sector"],
            "bias": row["bias"],
            "recent_accuracy": safe_float(row["recent_accuracy"], default=0),
        }
        for row in rows
    ]


async def get_ticker_insights(ticker: str | None = None) -> list[dict]:
    """Get ticker insights."""
    db = await get_db()

    if ticker:
        rows = await db.fetch_all(
            """
            SELECT ticker, recent_accuracy
            FROM ticker_insights WHERE UPPER(ticker) = $1
        """,
            ticker.upper(),
        )
    else:
        rows = await db.fetch_all("""
            SELECT ticker, recent_accuracy
            FROM ticker_insights ORDER BY recent_accuracy DESC
        """)

    return [
        {
            "ticker": row["ticker"],
            "recent_accuracy": safe_float(row["recent_accuracy"], default=0),
        }
        for row in rows
    ]


async def get_midday_patterns() -> dict:
    """Get midday adjustment patterns from learnings."""
    db = await get_db()
    row = await db.fetch_one("""
        SELECT days_with_midday, adjustment_win_rate, when_helpful,
               when_harmful, average_improvement, updated_at
        FROM midday_patterns ORDER BY updated_at DESC LIMIT 1
    """)
    if not row:
        return {}
    _check_staleness(row.get("updated_at"), "midday_patterns")
    return {
        "days_with_midday": row["days_with_midday"],
        "adjustment_win_rate": safe_float(row["adjustment_win_rate"], default=0),
        "when_helpful": row["when_helpful"] or [],
        "when_harmful": row["when_harmful"] or [],
        "average_improvement": safe_float(row["average_improvement"], default=0),
    }


async def get_mode_compliance() -> dict:
    """Get trading mode compliance patterns."""
    db = await get_db()
    row = await db.fetch_one("""
        SELECT mode_compliance_rate, mode_appropriate_win_rate, updated_at
        FROM trading_mode_patterns ORDER BY updated_at DESC LIMIT 1
    """)
    if row:
        _check_staleness(row.get("updated_at"), "trading_mode_patterns")
    violations = await db.fetch_all("""
        SELECT violation_text FROM mode_violations ORDER BY created_at DESC LIMIT 10
    """)
    return {
        "compliance_rate": safe_float(row["mode_compliance_rate"], default=0) if row else 0,
        "win_rate_when_compliant": safe_float(row["mode_appropriate_win_rate"], default=0)
        if row
        else 0,
        "recent_violations": [v["violation_text"] for v in violations] if violations else [],
    }


async def get_rotation_patterns(sector: str | None = None) -> dict:
    """Get sector rotation patterns from learnings."""
    db = await get_db()

    if sector:
        row = await db.fetch_one(
            """
            SELECT rss.as_hot_accuracy, rss.as_cold_accuracy
            FROM rotation_sector_scores rss
            JOIN sectors s ON s.id = rss.sector_id
            WHERE LOWER(s.name) = $1
        """,
            sector.lower(),
        )
        if not row:
            return {"sector": sector, "as_hot_accuracy": 0, "as_cold_accuracy": 0}
        return {
            "sector": sector,
            "as_hot_accuracy": safe_float(row["as_hot_accuracy"], default=0),
            "as_cold_accuracy": safe_float(row["as_cold_accuracy"], default=0),
        }

    row = await db.fetch_one("""
        SELECT total_days, overall_accuracy, hot_hit_rate, cold_hit_rate,
               avg_hot_vs_market, avg_cold_vs_market, updated_at
        FROM rotation_patterns ORDER BY updated_at DESC LIMIT 1
    """)
    if row:
        _check_staleness(row.get("updated_at"), "rotation_patterns")
    sector_rows = await db.fetch_all("""
        SELECT s.name, rss.as_hot_accuracy, rss.as_cold_accuracy
        FROM rotation_sector_scores rss JOIN sectors s ON s.id = rss.sector_id
    """)
    result = {
        "total_days": row["total_days"] if row else 0,
        "overall_accuracy": safe_float(row["overall_accuracy"], default=0) if row else 0,
        "hot_hit_rate": safe_float(row["hot_hit_rate"], default=0) if row else 0,
        "cold_hit_rate": safe_float(row["cold_hit_rate"], default=0) if row else 0,
        "avg_hot_vs_market": safe_float(row["avg_hot_vs_market"], default=0) if row else 0,
        "avg_cold_vs_market": safe_float(row["avg_cold_vs_market"], default=0) if row else 0,
    }
    result["sector_scores"] = (
        {
            r["name"]: {
                "as_hot": safe_float(r["as_hot_accuracy"], default=0),
                "as_cold": safe_float(r["as_cold_accuracy"], default=0),
            }
            for r in sector_rows
        }
        if sector_rows
        else {}
    )
    return result


async def get_macro_patterns() -> dict:
    """Get macro regime patterns from learnings."""
    db = await get_db()
    row = await db.fetch_one("""
        SELECT total_days, overall_accuracy, false_alarms, missed_drops,
               missed_opportunities, updated_at
        FROM macro_patterns ORDER BY updated_at DESC LIMIT 1
    """)
    if row:
        _check_staleness(row.get("updated_at"), "macro_patterns")
    regime_rows = await db.fetch_all("""
        SELECT regime, days_count, correct_count, avg_vn_change
        FROM macro_regime_accuracy
    """)
    result = {
        "total_days": row["total_days"] if row else 0,
        "overall_accuracy": safe_float(row["overall_accuracy"], default=0) if row else 0,
        "false_alarms": row["false_alarms"] if row else 0,
        "missed_drops": row["missed_drops"] if row else 0,
        "missed_opportunities": (row.get("missed_opportunities") or 0) if row else 0,
    }
    result["regime_accuracy"] = (
        {
            r["regime"]: {
                "days": r["days_count"],
                "correct": r["correct_count"],
                "avg_vn_change": safe_float(r["avg_vn_change"], default=0),
            }
            for r in regime_rows
        }
        if regime_rows
        else {}
    )
    return result


async def get_calibration_insights() -> CalibrationInsightsRow:
    """Get most recent calibration insights (entry precision, stop adequacy, R:R accuracy).

    Includes `last_trade_exit_date`, `swing_sample_size`, and a derived
    `staleness_days` so callers can drive the LLM staleness banner from a
    single row read.
    """
    db = await get_db()
    row = await db.fetch_one(
        """SELECT avg_entry_gap_pct, pct_entries_unreachable, avg_stop_vs_atr,
                  pct_stops_too_tight, avg_predicted_rr, avg_actual_rr,
                  target_hit_rate, sample_size, scan_date,
                  last_trade_exit_date, swing_sample_size
           FROM calibration_insights ORDER BY scan_date DESC LIMIT 1"""
    )
    if not row:
        return {}
    _check_staleness(row.get("scan_date"), "calibration_insights")

    last_trade_exit_date = row.get("last_trade_exit_date")
    staleness_days: int | None = None
    if last_trade_exit_date is not None:
        exit_date = (
            last_trade_exit_date.date()
            if hasattr(last_trade_exit_date, "date") and not isinstance(last_trade_exit_date, date)
            else last_trade_exit_date
        )
        staleness_days = (date.today() - exit_date).days

    # All ratio fields use `or None` so a NULL DB column (post phantom-guard)
    # surfaces as None, not 0. `as_of` and `sample_size` are always present.
    return {
        "avg_entry_gap_pct": safe_float(row.get("avg_entry_gap_pct")) or None,
        "pct_entries_unreachable": safe_float(row.get("pct_entries_unreachable")) or None,
        "avg_stop_vs_atr": safe_float(row.get("avg_stop_vs_atr")) or None,
        "pct_stops_too_tight": safe_float(row.get("pct_stops_too_tight")) or None,
        "avg_predicted_rr": safe_float(row.get("avg_predicted_rr")) or None,
        "avg_actual_rr": safe_float(row.get("avg_actual_rr")) or None,
        "target_hit_rate": safe_float(row.get("target_hit_rate")) or None,
        "sample_size": row.get("sample_size"),
        "swing_sample_size": row.get("swing_sample_size"),
        "last_trade_exit_date": str(last_trade_exit_date) if last_trade_exit_date else None,
        "staleness_days": staleness_days,
        "as_of": str(row["scan_date"]),
    }


async def get_strategy_regime_stats() -> list[dict]:
    """Get win rate by strategy x regime from v_strategy_regime_performance view."""
    db = await get_db()
    rows = await db.fetch_all("""
        SELECT strategy, market_regime as regime, trades as total_trades,
               ROUND(win_rate * 100, 1) as win_rate_pct,
               avg_return_pct as avg_pnl_pct
        FROM v_strategy_regime_performance
        WHERE trades >= 3
        ORDER BY win_rate_pct DESC
    """)
    return [dict(r) for r in rows] if rows else []


async def get_rolling_performance() -> dict:
    """Get rolling performance windows from v_rolling_performance view."""
    db = await get_db()
    row = await db.fetch_one("""
        SELECT * FROM v_rolling_performance LIMIT 1
    """)
    return dict(row) if row else {}


# ============================================================================
# Sync Wrappers
# ============================================================================

get_learnings_summary_sync = make_sync(get_learnings_summary)
get_winning_patterns_sync = make_sync(get_winning_patterns)
get_losing_patterns_sync = make_sync(get_losing_patterns)
get_sector_insights_sync = make_sync(get_sector_insights)
get_ticker_insights_sync = make_sync(get_ticker_insights)
get_midday_patterns_sync = make_sync(get_midday_patterns)
get_mode_compliance_sync = make_sync(get_mode_compliance)
get_rotation_patterns_sync = make_sync(get_rotation_patterns)
get_macro_patterns_sync = make_sync(get_macro_patterns)
