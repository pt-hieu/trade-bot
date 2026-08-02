"""
Learnings management and update logic.
Extracted from retrospective.py for the 300-line file limit.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from agents.retro.compute import compute_split_win_rates
from agents.retro.won import ENTRY_ACTIONS, compute_won
from shared.trading_config import get_trading_config

logger = logging.getLogger(__name__)

from .evaluation_loaders import (
    batch_fetch_evaluations,
    batch_fetch_macro_evals,
    batch_fetch_midday,
    batch_fetch_midday_summaries,
    batch_fetch_recommendations,
    batch_fetch_rotation_evals,
    batch_fetch_violations,
)
from .learnings_stats import calc_midday_adjustment_stats, calc_mode_appropriate_win_rate
from .macro_patterns import calculate_macro_patterns, calculate_rotation_patterns

ROLLING_WINDOW_DAYS = 30
MAX_PATTERNS_PER_TYPE = 5


def _to_float(val: Any) -> Any:
    """Convert Decimal → float so dicts are serializable."""
    if isinstance(val, Decimal):
        return float(val)
    return val


def _sanitize(d: dict) -> dict:
    """Convert Decimal values in a dict to float."""
    return {k: _to_float(v) for k, v in d.items()}


def _merge_patterns(
    existing: list[dict],
    new: list[dict],
    max_patterns: int = MAX_PATTERNS_PER_TYPE,
) -> list[dict]:
    """Merge new patterns into existing, deduplicating by description similarity."""
    merged = {p["pattern"].lower().strip(): dict(p) for p in existing}

    for p in new:
        key = p["pattern"].lower().strip()
        if key in merged:
            merged[key].update(
                {
                    "win_rate": p.get("win_rate", merged[key].get("win_rate", 0)),
                    "loss_rate": p.get("loss_rate", merged[key].get("loss_rate", 0)),
                    "sample_size": p.get("sample_size", merged[key].get("sample_size", 0)),
                    "actionable_rule": p.get("actionable_rule")
                    or merged[key].get("actionable_rule", ""),
                    "avoid_rule": p.get("avoid_rule") or merged[key].get("avoid_rule", ""),
                }
            )
        else:
            merged[key] = dict(p)

    sorted_patterns = sorted(merged.values(), key=lambda p: p.get("sample_size", 0), reverse=True)
    return sorted_patterns[:max_patterns]


async def load_learnings_from_db(
    days: int = ROLLING_WINDOW_DAYS,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Load daily records from DB and build learnings dict.

    Two modes:
    - Rolling window (default): loads last N `days` from today
    - Explicit range: when `start_date` and `end_date` are provided,
      loads records in [start_date, end_date) — used by checkpoint comparisons
    """
    from shared.database import get_db

    if start_date is not None and end_date is not None:
        window_days = (end_date - start_date).days
        range_start = start_date
        range_end = end_date
    else:
        window_days = days
        range_start = date.today() - timedelta(days=days)
        range_end = None  # no upper bound for rolling window

    scaffold: dict = {
        "last_updated": "",
        "rolling_window_days": window_days,
        "summary": {
            "total_days": 0,
            "total_recs": 0,
            "overall_entry_hit_rate": 0.0,
            "overall_win_rate": 0.0,
            "avg_pnl_percent": 0.0,
        },
        "winning_patterns": [],
        "losing_patterns": [],
        "sector_insights": [],
        "ticker_insights": [],
        "daily_records": [],
    }

    db = await get_db()

    if range_end is not None:
        rows = await db.fetch_all(
            """
            SELECT id, record_date::text AS record_date, total_recs,
                   entry_hit_rate, win_rate, best_call, worst_call,
                   key_insight, trading_mode::text AS trading_mode,
                   mode_compliance
            FROM daily_records
            WHERE record_date >= $1 AND record_date < $2
            ORDER BY record_date ASC
            """,
            range_start,
            range_end,
        )
    else:
        rows = await db.fetch_all(
            """
            SELECT id, record_date::text AS record_date, total_recs,
                   entry_hit_rate, win_rate, best_call, worst_call,
                   key_insight, trading_mode::text AS trading_mode,
                   mode_compliance
            FROM daily_records
            WHERE record_date >= $1
            ORDER BY record_date ASC
            """,
            range_start,
        )

    if not rows:
        return scaffold

    # Batch-fetch all child data upfront (9 queries total instead of ~177)
    record_ids = [row["id"] for row in rows]
    all_evals = await batch_fetch_evaluations(db, record_ids)
    all_recs = await batch_fetch_recommendations(db, record_ids)
    all_violations = await batch_fetch_violations(db, record_ids)
    all_midday = await batch_fetch_midday(db, record_ids)
    all_midday_summaries = await batch_fetch_midday_summaries(db, record_ids)
    all_rotation = await batch_fetch_rotation_evals(db, record_ids)
    all_macro = await batch_fetch_macro_evals(db, record_ids)

    # Assemble learnings from pre-fetched data (pure dict lookups, no await)
    learnings = scaffold
    for row in rows:
        record_id = row["id"]
        date_str = row["record_date"]

        eval_list = [_sanitize(e) for e in all_evals.get(record_id, [])]

        rec_list = []
        for r in all_recs.get(record_id, []):
            rec_list.append(
                {
                    "ticker": r["ticker"],
                    "action": r["action"],
                    "entry_price": float(r["entry_price_vnd"]) if r["entry_price_vnd"] else None,
                    "stop_price": float(r["stop_price_vnd"]) if r["stop_price_vnd"] else None,
                    "target_price": float(r["target_price_vnd"]) if r["target_price_vnd"] else None,
                    "size_shares": r["size_shares"],
                    "rationale": r["rationale"],
                    "section": r["section"],
                }
            )

        violations = all_violations.get(record_id, [])
        midday_db = all_midday.get(record_id)
        midday_sum_row = all_midday_summaries.get(record_id)
        midday_summary = _sanitize(midday_sum_row) if midday_sum_row else {}

        day_summary = {
            "total_recs": row["total_recs"] or 0,
            "entry_hit_rate": float(row["entry_hit_rate"] or 0),
            "win_rate": float(row["win_rate"] or 0),
            "best_call": row["best_call"] or "",
            "worst_call": row["worst_call"] or "",
            "key_insight": row["key_insight"] or "",
        }

        evaluations_dict = {
            "evaluations": eval_list,
            "day_summary": day_summary,
            "midday_summary": midday_summary,
            "mode_compliance": (
                row["mode_compliance"] if row["mode_compliance"] is not None else True
            ),
            "mode_violations": [v["violation_text"] for v in violations],
        }

        midday_for_update = None
        if midday_db:
            entries_count = midday_db["entries_hit"] or 0
            midday_for_update = {
                "trading_mode": midday_db["trading_mode"],
                "entries_hit": [None] * entries_count,  # len() used by update_learnings
                "afternoon_plan": midday_db["afternoon_plan"],
            }

        learnings = update_learnings(
            learnings,
            date_str,
            rec_list,
            evaluations_dict,
            {},  # empty patterns — extracted fresh in retrospective
            midday_data=midday_for_update,
            rotation_eval=all_rotation.get(record_id),
            macro_eval=all_macro.get(record_id),
        )

    return learnings


def update_learnings(
    learnings: dict,
    date: str,
    recommendations: list,
    evaluations: dict,
    patterns: dict,
    midday_data: dict | None = None,
    rotation_eval: dict | None = None,
    macro_eval: dict | None = None,
) -> dict:
    """Update learnings with today's data."""
    # Fill missing won values via canonical compute_won() (handles historical DB rows)
    hold_threshold = get_trading_config().hold_loss_threshold_pct
    evaluation_list = evaluations.get("evaluations", [])
    for evaluation in evaluation_list:
        if evaluation.get("won") is None:
            computed_won = compute_won(evaluation, hold_loss_threshold_pct=hold_threshold)
            if computed_won is not None:
                logger.info(
                    "Backfilled won=%s for %s (status=%s)",
                    computed_won,
                    evaluation.get("ticker"),
                    evaluation.get("status"),
                )
            evaluation["won"] = computed_won

    from midday.formatter import format_afternoon_plan_prose

    afternoon_plan_list = midday_data.get("afternoon_plan") if midday_data else None
    if not isinstance(afternoon_plan_list, list):
        afternoon_plan_list = []
    afternoon_plan_prose = (
        format_afternoon_plan_prose(
            afternoon_plan_list,
            (midday_data or {}).get("afternoon_note"),
        )
        if midday_data
        else None
    )

    daily_record = {
        "date": date,
        "recommendations": recommendations,
        "evaluations": evaluation_list,
        "day_summary": evaluations.get("day_summary", {}),
        "midday_data": {
            "trading_mode": midday_data.get("trading_mode") if midday_data else None,
            "entries_hit": len(midday_data.get("entries_hit", [])) if midday_data else 0,
            # Structured list for future readers, pre-rendered prose side-field
            # so existing text-matching consumers keep working.
            "afternoon_plan": afternoon_plan_list,
            "afternoon_plan_prose": afternoon_plan_prose,
        }
        if midday_data
        else None,
        "midday_summary": evaluations.get("midday_summary", {}),
        "mode_compliance": evaluations.get("mode_compliance", True),
        "mode_violations": evaluations.get("mode_violations", []),
        "rotation_evaluation": rotation_eval,
        "macro_evaluation": macro_eval,
    }

    existing_dates = {r["date"] for r in learnings["daily_records"]}
    if date in existing_dates:
        learnings["daily_records"] = [
            daily_record if r["date"] == date else r for r in learnings["daily_records"]
        ]
    else:
        learnings["daily_records"].append(daily_record)

    learnings["daily_records"] = sorted(learnings["daily_records"], key=lambda x: x["date"])[
        -ROLLING_WINDOW_DAYS:
    ]

    all_evals = [e for r in learnings["daily_records"] for e in r.get("evaluations", [])]
    counted_evals = [e for e in all_evals if e.get("won") is not None]
    total_recs = len(counted_evals)

    actionable = [e for e in all_evals if e.get("recommendation") in ENTRY_ACTIONS]
    entered = [e for e in actionable if e.get("entry_hit")]
    entry_hit_rate = len(entered) / len(actionable) * 100 if actionable else None

    wins = [e for e in counted_evals if e.get("won")]
    win_rate = len(wins) / total_recs * 100 if total_recs > 0 else 0.0

    split_rates = compute_split_win_rates(counted_evals)
    swing_win_rate = split_rates["swing_win_rate"]
    longterm_win_rate = split_rates["longterm_win_rate"]
    swing_sample_size = split_rates["swing_sample_size"]

    pnl_values = [e.get("pnl_percent", 0) for e in entered if e.get("pnl_percent") is not None]
    avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

    learnings["summary"] = {
        "total_days": len(learnings["daily_records"]),
        "total_recs": total_recs,
        "total_actionable": len(actionable),
        "overall_entry_hit_rate": round(entry_hit_rate, 2) if entry_hit_rate is not None else None,
        "overall_win_rate": round(win_rate, 2),
        "avg_pnl_percent": round(avg_pnl, 2),
        "swing_win_rate": swing_win_rate,
        "longterm_win_rate": longterm_win_rate,
        "swing_sample_size": swing_sample_size,
    }

    if patterns.get("winning_patterns"):
        learnings["winning_patterns"] = _merge_patterns(
            learnings.get("winning_patterns", []),
            patterns["winning_patterns"],
        )
    if patterns.get("losing_patterns"):
        learnings["losing_patterns"] = _merge_patterns(
            learnings.get("losing_patterns", []),
            patterns["losing_patterns"],
        )
    if patterns.get("sector_insights"):
        learnings["sector_insights"] = patterns["sector_insights"]
    if patterns.get("ticker_insights"):
        learnings["ticker_insights"] = patterns["ticker_insights"]
    if patterns.get("strategy_insights"):
        learnings["strategy_patterns"] = {
            s["strategy"]: {
                "win_rate": s["win_rate"],
                "sample_size": s["sample_size"],
            }
            for s in patterns["strategy_insights"]
        }
    if patterns.get("calibration_insights"):
        learnings["calibration_insights"] = patterns["calibration_insights"]
    learnings["last_updated"] = date

    midday_records = [r for r in learnings["daily_records"] if r.get("midday_data")]
    if midday_records:
        mode_violations_all = [v for r in midday_records for v in r.get("mode_violations", [])]
        compliance_count = sum(1 for r in midday_records if r.get("mode_compliance", True))

        midday_stats = calc_midday_adjustment_stats(midday_records)
        learnings["midday_patterns"] = {
            "days_with_midday": len(midday_records),
            **midday_stats,
        }
        mode_win_rate = calc_mode_appropriate_win_rate(midday_records)
        learnings["trading_mode_patterns"] = {
            "mode_compliance_rate": compliance_count / len(midday_records),
            "mode_violations": mode_violations_all[:10],
            "mode_appropriate_win_rate": mode_win_rate,
        }
    else:
        learnings["midday_patterns"] = {
            "days_with_midday": 0,
            "adjustment_win_rate": 0.0,
            "when_helpful": [],
            "when_harmful": [],
            "average_improvement": 0.0,
        }
        learnings["trading_mode_patterns"] = {
            "mode_compliance_rate": 1.0,
            "mode_violations": [],
            "mode_appropriate_win_rate": 0.0,
        }

    rotation_records: list[dict] = [
        evaluation
        for r in learnings["daily_records"]
        if (evaluation := r.get("rotation_evaluation")) is not None
    ]
    learnings["rotation_patterns"] = calculate_rotation_patterns(rotation_records)

    macro_records: list[dict] = [
        evaluation
        for r in learnings["daily_records"]
        if (evaluation := r.get("macro_evaluation")) is not None
    ]
    learnings["macro_patterns"] = calculate_macro_patterns(macro_records)

    return learnings
