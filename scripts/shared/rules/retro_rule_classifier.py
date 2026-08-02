"""Deterministic retro-evaluation rule classifier.

Maps an already-computed retro evaluation dict to one canonical rule label.
Follows the `catalyst_classifier.py` precedent (2026-04-21 feedback memory):
LLM outputs bound to DB enums require a deterministic Python post-pass between
the agent and the DB. The LLM keeps its qualitative `analysis` free-text; the
rule label is computed here.

Rule vocabulary (first match wins — order matters):
  * SWING_TARGET_HIT          — swing entry, target reached
  * SWING_STOPPED             — swing entry or holding, stop breached
  * SWING_WIN                 — swing entry/hold, positive outcome (non-target)
  * SWING_LOSS                — swing entry/hold, negative outcome (non-stop)
  * SWING_PENDING             — swing entry filled, no target/stop yet
  * SWING_MISSED              — swing entry signal, entry price never reached
  * SWING_HOLD                — swing HOLD action, in-tolerance day move
  * LONGTERM_CATASTROPHIC     — longterm position, P/L below catastrophic floor
  * LONGTERM_THESIS_INTACT    — longterm position, held, above floor
  * LONGTERM_EXCLUDED         — longterm watchlist row (no actionable eval)
  * WATCH_MISS                — WATCH action, entry never triggered
  * WAIT_UNMET                — WAIT action, conditions never met
  * SKIP_CORRECT              — SKIP/AVOID action, structurally excluded
  * TRADE_EXECUTED_WIN        — manual trade closed in the black
  * TRADE_EXECUTED_LOSS       — manual trade closed in the red
  * UNCLASSIFIED              — fallback when no rule matches

The vocabulary is DB-enum-aligned: `migration 326` adds
`daily_evaluations.rule_applied` with exactly these values.
"""

from __future__ import annotations

from typing import Literal

from shared.observability_post_llm import emit_rule_outcome

# Mirrors `agents.retro.won.ENTRY_ACTIONS` / `EXCLUDED_ACTIONS`. Duplicated
# to avoid a circular import — `agents.retro` imports this module via
# `evaluator.py`, so we cannot import back up the package tree.
ENTRY_ACTIONS: frozenset[str] = frozenset({"BUY", "ADD", "LIMIT_BUY"})
EXCLUDED_ACTIONS: frozenset[str] = frozenset({"WATCH", "WAIT", "SKIP", "AVOID"})

RetroRule = Literal[
    "SWING_TARGET_HIT",
    "SWING_STOPPED",
    "SWING_WIN",
    "SWING_LOSS",
    "SWING_PENDING",
    "SWING_MISSED",
    "SWING_HOLD",
    "LONGTERM_CATASTROPHIC",
    "LONGTERM_THESIS_INTACT",
    "LONGTERM_EXCLUDED",
    "WATCH_MISS",
    "WAIT_UNMET",
    "SKIP_CORRECT",
    "TRADE_EXECUTED_WIN",
    "TRADE_EXECUTED_LOSS",
    "UNCLASSIFIED",
]

_HOLD_ACTIONS: frozenset[str] = frozenset({"HOLD", "EXIT", "TRIM"})


def classify_retro_rule(
    eval_row: dict,
    *,
    longterm_catastrophic_pct: float = 20.0,
) -> RetroRule:
    """Classify one evaluation row into one rule label.

    Args:
        eval_row: Evaluation dict produced by `compute_evaluations`. Required
            keys checked: `plan_type`, `recommendation`, `status`,
            `entry_hit`, `stop_hit`, `target_hit`, `pnl_percent`,
            `day_change`, `trade_executed`, `actual_pl_pct`.
        longterm_catastrophic_pct: Floor below which LONGTERM positions are
            classified CATASTROPHIC. Default mirrors `trading_config`.

    Returns:
        A `RetroRule` literal — never None, never a free string. Unknown
        shapes map to `UNCLASSIFIED` so DB enum writes still succeed.
    """
    plan_type = (eval_row.get("plan_type") or "").upper()
    action = (eval_row.get("recommendation") or "").upper()
    status = (eval_row.get("status") or "").upper()
    entry_hit = bool(eval_row.get("entry_hit"))
    stop_hit = bool(eval_row.get("stop_hit"))
    target_hit = bool(eval_row.get("target_hit"))
    pnl_percent = eval_row.get("pnl_percent")
    day_change = eval_row.get("day_change")
    trade_executed = bool(eval_row.get("trade_executed"))
    actual_pl_pct = eval_row.get("actual_pl_pct")

    # Rule A — trade execution takes precedence when the trade actually closed.
    # Signal vs. execution divergence is informative even when the morning
    # recommendation was a HOLD/EXIT/TRIM.
    if trade_executed:
        if isinstance(actual_pl_pct, (int, float)) and actual_pl_pct > 0:
            return "TRADE_EXECUTED_WIN"
        if isinstance(actual_pl_pct, (int, float)) and actual_pl_pct < 0:
            return "TRADE_EXECUTED_LOSS"
        # Zero or missing pnl on an executed trade — bucket as WIN to avoid
        # false LOSS labeling; rare edge case. Emit so dashboards can spot
        # the atypical path.
        emit_rule_outcome(
            "retro_rule",
            "coerced",
            agent="retro_rule_classifier",
            reason="trade_executed_zero_pnl",
            boundary="classifier",
            metadata={"actual_pl_pct": str(actual_pl_pct)},
        )
        return "TRADE_EXECUTED_WIN"

    # Rule B — longterm plan-type dominates over action bucketing.
    if plan_type == "LONGTERM":
        if status == "EXCLUDED":
            return "LONGTERM_EXCLUDED"
        if isinstance(pnl_percent, (int, float)) and pnl_percent <= -abs(longterm_catastrophic_pct):
            emit_rule_outcome(
                "retro_rule",
                "coerced",
                agent="retro_rule_classifier",
                reason="longterm_catastrophic",
                boundary="classifier",
                metadata={"pnl_percent": float(pnl_percent)},
            )
            return "LONGTERM_CATASTROPHIC"
        return "LONGTERM_THESIS_INTACT"

    # Rule C — structurally EXCLUDED actions split into three buckets:
    # WATCH never entered, WAIT conditions unmet, SKIP/AVOID structurally out.
    if action in EXCLUDED_ACTIONS:
        if action == "WATCH":
            return "WATCH_MISS"
        if action == "WAIT":
            return "WAIT_UNMET"
        return "SKIP_CORRECT"

    # Rule D — swing entry actions (BUY/ADD/LIMIT_BUY): resolve by hit flags.
    if action in ENTRY_ACTIONS:
        if target_hit:
            return "SWING_TARGET_HIT"
        if stop_hit:
            return "SWING_STOPPED"
        if not entry_hit:
            return "SWING_MISSED"
        if status == "WIN":
            return "SWING_WIN"
        if status == "LOSS":
            return "SWING_LOSS"
        return "SWING_PENDING"

    # Rule E — swing HOLD-family actions.
    if action in _HOLD_ACTIONS:
        if stop_hit or status == "STOP_BREACHED":
            return "SWING_STOPPED"
        # When pnl_percent carries the position-level P/L, branch on sign.
        if isinstance(pnl_percent, (int, float)) and pnl_percent > 0:
            return "SWING_WIN"
        if isinstance(pnl_percent, (int, float)) and pnl_percent < 0:
            return "SWING_LOSS"
        # Day-change based when position P/L is unavailable.
        if isinstance(day_change, (int, float)) and day_change >= 0:
            return "SWING_HOLD"
        if isinstance(day_change, (int, float)):
            return "SWING_LOSS"
        return "SWING_HOLD"

    # Severity defaults to INFO; if a measured baseline shows >10%
    # unclassified rate, the helper exposes ``unclassified_as_debug=True``.
    emit_rule_outcome(
        "retro_rule",
        "unclassified",
        agent="retro_rule_classifier",
        reason="unknown_action" if action else "unknown_rule",
        boundary="classifier",
        metadata={"action": action, "plan_type": plan_type, "status": status},
    )
    return "UNCLASSIFIED"
