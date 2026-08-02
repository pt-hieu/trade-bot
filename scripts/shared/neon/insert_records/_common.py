"""Shared helpers for insert_records package.

Hosts the normalizers + SQL constants + row builder used by both `morning.py`
and `daily.py`. Also re-exports `_is_valid_ticker` from `..ticker_extract`
so package consumers (including test fixtures) keep a single import point.
"""

from __future__ import annotations

import logging

from shared.rules.exit_strategy import exit_state_from_rec, resolve_exit_strategy
from shared.rules.plan_shape import coerce_plan_shape_for_check
from shared.rules.row_invariants import RowInvariantError
from shared.rules.row_invariants import daily_evaluations as _daily_evaluations_inv
from shared.rules.row_invariants import daily_recommendations as _daily_recs_inv

from ...ticker_extract import is_valid_ticker as _is_valid_ticker
from ...vn_universe import is_vn_listed

logger = logging.getLogger(__name__)

__all__ = [
    "_INSERT_REC_SQL",
    "INSERT_EVAL_SQL",
    "_build_eval_row",
    "_build_rec_row",
    "_is_valid_ticker",
    "_normalize_action",
    "_normalize_eval_status",
    "_normalize_trading_mode",
    "_vnd_int",
]


_VALID_EVAL_STATUSES = frozenset(
    {
        "WIN",
        "LOSS",
        "PENDING",
        "MISSED",
        "HOLD",
        "WATCH",
        "WAIT",
        "EXIT",
        "MISS",
        "STOP_BREACHED",
        "EXCLUDED",
    }
)


def _normalize_eval_status(status: str | None, *, ticker: str | None = None) -> str | None:
    """Normalize eval status string to a valid DB enum value, or None.

    Unknown statuses log a warning naming the offending ticker and downgrade to
    PENDING so a bad LLM response doesn't break the retro insert.
    """
    if not status:
        return status
    if status.upper() in _VALID_EVAL_STATUSES:
        return status
    logger.warning(
        "Unknown eval status '%s' for %s, defaulting to PENDING",
        status,
        ticker or "<unknown ticker>",
    )
    return "PENDING"


_VALID_TRADING_MODES = {"NORMAL", "LOW_CASH", "REALLOCATION"}


def _normalize_trading_mode(mode: str | None) -> str | None:
    """Normalize trading_mode to a valid DB enum value, or None."""
    if not mode:
        return None
    upper = mode.upper()
    if upper in _VALID_TRADING_MODES:
        return upper
    logger.warning("Invalid trading_mode %r, defaulting to NORMAL", mode)
    return "NORMAL"


def _normalize_action(action: str | None) -> str | None:
    """Normalize action string to valid rec_action enum value."""
    if not action:
        return None

    valid_actions = {
        "BUY",
        "SELL",
        "HOLD",
        "WATCH",
        "WAIT",
        "SKIP",
        "AVOID",
        "LIMIT_BUY",
        "EXIT",
        "TRIM",
        "ADD",
        "EVALUATE",
    }
    base_action = action.upper().split()[0].split("@")[0].strip()

    if "LIMIT" in action.upper() and "BUY" in action.upper():
        base_action = "LIMIT_BUY"

    if base_action in valid_actions:
        return base_action
    logger.warning(
        "_normalize_action: unknown action %r (base=%r) — defaulting to WATCH",
        action,
        base_action,
    )
    return "WATCH"


def _vnd_int(value: object) -> int | None:
    """Convert a price value to VND integer, or None if missing / non-numeric.

    Accepts float/int/str (LLM output may emit any of these) and falls back to
    None on anything that can't be coerced. `object` is intentional: rec dicts
    come from untyped LLM output, so the type guard lives here, not at the
    caller.
    """
    if not value:
        return None
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


_VALID_PLAN_TYPES = frozenset({"SWING", "LONGTERM"})


def _resolve_plan_type(rec: dict[str, object]) -> str:
    """Pick plan_type for a recommendation row.

    Priority: explicit rec.plan_type > section heuristic > SWING default. The
    section heuristic mirrors the migration 317 backfill so new rows land in the
    same slice as historical ones. Invalid values log and downgrade to SWING
    rather than raising — the DB CHECK constraint is the hard gate.
    """
    explicit = rec.get("plan_type")
    if isinstance(explicit, str) and explicit.upper() in _VALID_PLAN_TYPES:
        return explicit.upper()
    section = rec.get("section")
    if isinstance(section, str) and section == "LONG_TERM":
        return "LONGTERM"
    if explicit is not None:
        logger.warning(
            "Invalid plan_type %r on ticker %r — defaulting to SWING",
            explicit,
            rec.get("ticker"),
        )
    return "SWING"


_INSERT_REC_SQL = """
    INSERT INTO daily_recommendations (
        record_id, ticker, action, entry_price_vnd, stop_price_vnd,
        target_price_vnd, size_shares, rationale, section,
        strategy, strategy_confidence,
        risk_reward, verdict,
        volume_vs_avg, volume_confirmed, pattern_name,
        sim_ev, sim_p_target, sim_p_stop,
        belief_conviction, source, urgency, counter_thesis,
        atr_at_entry_vnd, trail_mult, plan_type,
        trigger_price_vnd, plan_shape, invalidation_note,
        gate_floor_at_build, gate_passes_at_build
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
        $12, $13, $14, $15, $16, $17, $18, $19,
        $20, $21, $22, $23, $24, $25, $26,
        $27, $28, $29, $30, $31
    )
"""


INSERT_EVAL_SQL = """
    INSERT INTO daily_evaluations (
        record_id, ticker, recommendation, section, entry_hit, stop_hit,
        target_hit, eod_price_vnd, pnl_percent, status, analysis, won,
        day_change, entry_gap_pct, predicted_rr, actual_max_rr,
        stop_buffer_pct, stop_vs_atr_ratio, atr_pct,
        trade_executed, actual_exit_price_vnd, actual_pl_pct,
        actual_pl_net_vnd, strategy, plan_type, rule_applied,
        stop_price_vnd
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
        $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26,
        $27
    )
"""


def _build_rec_row(
    record_id: int,
    rec: dict[str, object],
    vn_universe: frozenset[str] | None = None,
) -> tuple[object, ...] | None:
    """Build a parameter tuple for _INSERT_REC_SQL, or None if invalid.

    ``vn_universe`` is the set returned by
    :func:`shared.vn_universe.load_vn_universe_async`. When supplied, the
    ticker must pass both the regex shape check AND be a member — closes
    the sibling of ISSUE-2026-04-24-005. When ``None`` (e.g. a legacy test
    that didn't prime the universe), shape-only validation is retained.
    """
    raw_ticker = rec.get("ticker")
    raw_action = rec.get("action")
    ticker = raw_ticker if isinstance(raw_ticker, str) else None
    action_input = raw_action if isinstance(raw_action, str) else None
    action = _normalize_action(action_input)
    if not (ticker and action and _is_valid_ticker(ticker)):
        if ticker:
            logger.warning("Skipping invalid rec: ticker=%r action=%r", ticker, action)
        return None
    if vn_universe is not None and not is_vn_listed(ticker, vn_universe):
        logger.warning("Skipping non-VN rec ticker=%r (not in universe)", ticker)
        return None

    rec_strategy = rec.get("strategy")
    strategy_str: str | None = rec_strategy if isinstance(rec_strategy, str) else None
    exit_cols = resolve_exit_strategy(strategy_str).to_db_row(exit_state_from_rec(rec))

    # WATCH/WAIT mirror trigger→entry so renderers display a tradeable level.
    # Safe: retro evaluator gates on ENTRY_ACTIONS (BUY/ADD/LIMIT_BUY) before
    # reading entry_price_vnd. See agents/retro/compute/evaluation.py:220.
    trigger_vnd = _vnd_int(rec.get("trigger_price"))
    entry_vnd_raw = _vnd_int(rec.get("entry_price"))
    entry_for_db = trigger_vnd if (action in ("WATCH", "WAIT") and trigger_vnd) else entry_vnd_raw

    raw_shape = rec.get("plan_shape")
    plan_shape_str: str | None = raw_shape.upper() or None if isinstance(raw_shape, str) else None

    # Single source of truth: shared/rules/plan_shape.py. Boundary guard
    # applies the same rule as the producer-side call sites — strict=False
    # so production stays smooth (a slipped-through producer regression
    # surfaces in Logfire as `plan_shape_coerced` rather than crashing
    # the whole executemany batch).
    plan_shape = coerce_plan_shape_for_check(
        plan_shape_str,
        action,
        trigger_vnd,
        strict=False,
    )

    row = (
        record_id,
        ticker,
        action,
        entry_for_db,
        _vnd_int(rec.get("stop_price")),
        exit_cols.get("target_price_vnd"),
        rec.get("size_shares"),
        rec.get("rationale"),
        rec.get("section"),
        rec.get("strategy"),
        rec.get("strategy_confidence"),
        rec.get("risk_reward"),
        rec.get("verdict"),
        rec.get("volume_vs_avg"),
        rec.get("volume_confirmed"),
        rec.get("pattern_name"),
        rec.get("sim_ev"),
        rec.get("sim_p_target"),
        rec.get("sim_p_stop"),
        rec.get("belief_conviction"),
        rec.get("source"),
        rec.get("urgency"),
        rec.get("counter_thesis"),
        exit_cols.get("atr_at_entry_vnd"),
        exit_cols.get("trail_mult"),
        _resolve_plan_type(rec),
        trigger_vnd,
        plan_shape,
        rec.get("invalidation_note"),
        rec.get("gate_floor_at_build"),
        rec.get("gate_passes_at_build"),
    )

    # Structural mirror of every DB CHECK on daily_recommendations. Coerce
    # in order; if violations remain after one pass, raise — the producer
    # emitted an unfixable row that would have rolled back the batch.
    violations = _daily_recs_inv.validate_row(row)
    for v in violations:
        if v.suggested_coercion is not None:
            row = v.suggested_coercion(row)
    residual = _daily_recs_inv.validate_row(row)
    if residual:
        raise RowInvariantError(
            f"daily_recommendations row invariant unfixable for ticker={ticker!r}: "
            f"{[v.constraint_name for v in residual]}"
        )
    return row


def _build_eval_row(
    record_id: int,
    eval_data: dict[str, object],
) -> tuple[object, ...] | None:
    """Build a parameter tuple for INSERT_EVAL_SQL, or None when invalid.

    Boundary guard for daily_evaluations CHECK constraints (migrations 326
    `rule_applied_check` + 333 `stop_price_vnd_check`). Extracted from
    `daily.py:108-138` — symmetric to `_build_rec_row`.
    """
    raw_ticker = eval_data.get("ticker")
    ticker = raw_ticker if isinstance(raw_ticker, str) else None
    raw_rec = eval_data.get("recommendation")
    recommendation = _normalize_action(raw_rec if isinstance(raw_rec, str) else None)
    if not (ticker and recommendation):
        return None

    eod_price = eval_data.get("eod_price")
    eod_vnd = int(eod_price * 1000) if isinstance(eod_price, (int, float)) and eod_price else None

    raw_status = eval_data.get("status")
    status = _normalize_eval_status(
        raw_status if isinstance(raw_status, str) else None, ticker=ticker
    )

    stop_kvnd = eval_data.get("stop_price")
    stop_price_vnd = (
        int(round(stop_kvnd * 1000)) if isinstance(stop_kvnd, (int, float)) and stop_kvnd else None
    )

    row = (
        record_id,
        ticker,
        recommendation,
        eval_data.get("section"),
        eval_data.get("entry_hit") or False,
        eval_data.get("stop_hit") or False,
        eval_data.get("target_hit") or False,
        eod_vnd,
        eval_data.get("pnl_percent"),
        status,
        eval_data.get("analysis"),
        eval_data.get("won"),
        eval_data.get("day_change"),
        eval_data.get("entry_gap_pct"),
        eval_data.get("predicted_rr"),
        eval_data.get("actual_max_rr"),
        eval_data.get("stop_buffer_pct"),
        eval_data.get("stop_vs_atr_ratio"),
        eval_data.get("atr_pct"),
        eval_data.get("trade_executed") or False,
        eval_data.get("actual_exit_price_vnd"),
        eval_data.get("actual_pl_pct"),
        eval_data.get("actual_pl_net_vnd"),
        eval_data.get("strategy"),
        eval_data.get("plan_type"),
        eval_data.get("rule_applied"),
        stop_price_vnd,
    )

    violations = _daily_evaluations_inv.validate_row(row)
    for v in violations:
        if v.suggested_coercion is not None:
            row = v.suggested_coercion(row)
    residual = _daily_evaluations_inv.validate_row(row)
    if residual:
        raise RowInvariantError(
            f"daily_evaluations row invariant unfixable for ticker={ticker!r}: "
            f"{[v.constraint_name for v in residual]}"
        )
    return row
