"""Deterministic evaluation computations for retrospective pipeline.

Module layout (post-modularisation, SWI-212):
  * ``trades.py`` — _build_closed_trade_map (ticker-aggregated trade map).
  * ``evaluation.py`` — compute_evaluations + _evaluate_single + _make_eval +
    plan-type constants + ENTRY_HIT_RATE_NA.
  * ``__init__.py`` — compute_split_win_rates + compute_day_summary + re-exports.
"""

from __future__ import annotations

from ..won import ENTRY_ACTIONS, HOLD_ACTIONS
from .evaluation import (
    ENTRY_HIT_RATE_NA,
    PLAN_TYPE_LONGTERM,
    PLAN_TYPE_SWING,
    _evaluate_single,
    _make_eval,
    compute_evaluations,
)
from .trades import _build_closed_trade_map


def compute_split_win_rates(evaluations: list[dict]) -> dict:
    """Compute swing/longterm win rates from evaluations with plan_type."""
    swing_total = swing_wins = longterm_total = longterm_wins = 0
    for evaluation in evaluations:
        plan_type = evaluation.get("plan_type")
        won = evaluation.get("won") is True
        if plan_type == PLAN_TYPE_SWING:
            swing_total += 1
            if won:
                swing_wins += 1
        elif plan_type == PLAN_TYPE_LONGTERM:
            longterm_total += 1
            if won:
                longterm_wins += 1

    return {
        "swing_win_rate": round(swing_wins / swing_total * 100, 1) if swing_total > 0 else None,
        "longterm_win_rate": round(longterm_wins / longterm_total * 100, 1)
        if longterm_total > 0
        else None,
        "swing_sample_size": swing_total,
    }


def _format_call(e: dict) -> str:
    """Format best/worst call string using the right metric for the action."""
    ticker = e["ticker"]
    action = e["recommendation"]
    if action.upper() in HOLD_ACTIONS:
        day = e.get("day_change", 0) or 0
        return f"{ticker} {action} (day:{day:+.1f}%)"
    pnl = e.get("pnl_percent", 0) or 0
    return f"{ticker} {action} ({pnl:+.1f}%)"


def _score_for_ranking(e: dict) -> float:
    """Score for best/worst call ranking — today's recommendation accuracy."""
    action = (e.get("recommendation") or "").upper()
    if action in ("TRIM", "EXIT"):
        day = e.get("day_change", 0) or 0
        return -day
    elif action in HOLD_ACTIONS:
        return e.get("day_change", 0) or 0
    return e.get("pnl_percent", 0) or 0


def compute_day_summary(evaluations: list[dict]) -> dict:
    """Compute day summary stats from pre-computed evaluations.

    Only counts actionable recs (BUY/ADD/HOLD/EXIT/TRIM) in win rate.
    SKIP/AVOID/WAIT/WATCH are excluded entirely.
    """
    actionable = [e for e in evaluations if e["status"] != "EXCLUDED"]
    countable = [
        e for e in actionable if e.get("has_entry_data") is not False and e.get("won") is not None
    ]
    total = len(countable)

    entry_recs = [e for e in evaluations if e["recommendation"] in ENTRY_ACTIONS]
    entered = [e for e in entry_recs if e["entry_hit"]]
    entry_hit_rate = len(entered) / len(entry_recs) * 100 if entry_recs else None

    wins = [e for e in countable if e.get("won") is True]
    win_rate = len(wins) / total * 100 if total > 0 else 0.0

    split_rates = compute_split_win_rates(countable)

    with_pnl = [e for e in countable if e.get("pnl_percent") is not None and e["pnl_percent"] != 0]
    best = max(with_pnl, key=_score_for_ranking) if with_pnl else None
    worst = min(with_pnl, key=_score_for_ranking) if with_pnl else None

    return {
        "total_recs": total,
        "entry_hit_rate": round(entry_hit_rate, 2) if entry_hit_rate is not None else None,
        "win_rate": round(win_rate, 2),
        "swing_win_rate": split_rates["swing_win_rate"],
        "longterm_win_rate": split_rates["longterm_win_rate"],
        "best_call": _format_call(best) if best else "None",
        "worst_call": _format_call(worst) if worst else "None",
        "key_insight": "",  # LLM fills this in
    }


__all__ = [
    "ENTRY_HIT_RATE_NA",
    "PLAN_TYPE_LONGTERM",
    "PLAN_TYPE_SWING",
    "_build_closed_trade_map",
    "_evaluate_single",
    "_make_eval",
    "compute_day_summary",
    "compute_evaluations",
    "compute_split_win_rates",
]
