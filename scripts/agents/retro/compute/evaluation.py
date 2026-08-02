"""Per-recommendation evaluation against EOD prices.

All numeric calculations are done in Python — LLM only generates
qualitative analysis text. See module docstring on stop semantics
(day-0 EOD scoring vs day-N intraday — kept divergent on purpose).
"""

from __future__ import annotations

import logging

from shared.neon import ClosedTradeEntry
from shared.rules.exit_strategy import ATR_TRAIL_STRATEGIES
from shared.trading_config import get_trading_config

from ..parser import SECTION_LONG_TERM
from ..won import (
    ALL_KNOWN_ACTIONS,
    ENTRY_ACTIONS,
    EXCLUDED_ACTIONS,
    HOLD_ACTIONS,
    UnknownActionError,
    compute_won,
)
from .trades import _build_closed_trade_map

logger = logging.getLogger(__name__)

# Plan type constants — controls HOLD win semantics in compute_won()
PLAN_TYPE_SWING = "SWING"
PLAN_TYPE_LONGTERM = "LONGTERM"

# Display string when no BUY/ADD/LIMIT_BUY recommendations exist to score
ENTRY_HIT_RATE_NA = "N/A (no entry actions)"


def compute_evaluations(
    recommendations: list[dict],
    eod_prices: dict,
    holdings: list | None = None,
    closed_trades: list[ClosedTradeEntry] | None = None,
) -> list[dict]:
    """Deterministically evaluate each recommendation against EOD prices."""
    trades_list: list[ClosedTradeEntry] = closed_trades if closed_trades else []
    closed_trade_map = _build_closed_trade_map(trades_list)
    from shared.neon import collapse_holdings_by_ticker

    holdings_by_ticker = collapse_holdings_by_ticker(holdings or [])
    evaluations = [
        _evaluate_single(rec, eod_prices, holdings_by_ticker, closed_trade_map)
        for rec in recommendations
    ]

    hold_threshold = get_trading_config().hold_loss_threshold_pct
    for evaluation in evaluations:
        evaluation["won"] = compute_won(
            evaluation,
            hold_loss_threshold_pct=hold_threshold,
            plan_type=evaluation.get("plan_type"),
        )

    missed = [e for e in evaluations if e.get("status") == "MISSED"]
    if missed and len(evaluations) > 0 and len(missed) > len(evaluations) * 0.3:
        logger.warning(
            f"High MISSED rate: {len(missed)}/{len(evaluations)} "
            f"({len(missed) / len(evaluations):.0%}) — "
            f"tickers: {[e['ticker'] for e in missed]}"
        )

    return evaluations


def _evaluate_single(
    rec: dict,
    prices: dict,
    holdings: dict | None = None,
    closed_trade_map: dict | None = None,
) -> dict:
    """Evaluate a single recommendation against EOD prices."""
    ticker = rec.get("ticker") or ""
    action = (rec.get("action") or "").upper()
    if action and action not in ALL_KNOWN_ACTIONS:
        raise UnknownActionError(
            f"Unknown recommendation action {action!r} for ticker {ticker!r}. "
            f"Add it to RecommendationAction Literal in scripts/agents/retro/won.py "
            f"and decide which action-set it belongs to (ENTRY/HOLD/EXCLUDED)."
        )
    section = rec.get("section") or ""
    raw_entry = rec.get("entry_price")
    raw_stop = rec.get("stop_price")
    raw_target = rec.get("target_price")
    entry_price = raw_entry / 1000 if raw_entry else None
    stop_price = raw_stop / 1000 if raw_stop else None
    target_price = raw_target / 1000 if raw_target else None
    strategy = rec.get("strategy")

    holding = (holdings or {}).get(ticker)
    raw_plan_type = rec.get("plan_type")
    if not raw_plan_type:
        raw_plan_type = holding.get("plan_type") if holding else None
    plan_type = raw_plan_type.upper() if raw_plan_type else None

    price_data = prices.get(ticker, {})

    if not price_data or "error" in price_data:
        return _make_eval(
            ticker,
            action,
            section=section,
            status="MISSED",
            analysis="No price data available",
            strategy=strategy,
            plan_type=plan_type,
        )

    eod_close = price_data.get("close") or 0
    eod_high = price_data.get("high") or 0
    eod_low = price_data.get("low") or 0
    eod_open = price_data.get("open") or 0

    if eod_close == 0:
        return _make_eval(
            ticker,
            action,
            section=section,
            status="MISSED",
            analysis="EOD price is 0 — likely failed fetch",
            strategy=strategy,
            plan_type=plan_type,
        )

    if section == SECTION_LONG_TERM:
        return _make_eval(
            ticker,
            action,
            section=section,
            eod_price=eod_close,
            status="EXCLUDED",
            entry_price=entry_price,
            strategy=strategy,
            plan_type=PLAN_TYPE_LONGTERM,
        )

    if action in EXCLUDED_ACTIONS:
        return _make_eval(
            ticker,
            action,
            section=section,
            eod_price=eod_close,
            status="EXCLUDED",
            entry_price=entry_price,
            strategy=strategy,
            plan_type=plan_type,
        )

    if action in HOLD_ACTIONS:
        closed_trade = (closed_trade_map or {}).get(ticker)
        if closed_trade:
            actual_exit_vnd = closed_trade.get("exit_price_vnd") or 0
            actual_pl_pct = closed_trade.get("pl_pct") or 0.0
            actual_pl_net = closed_trade.get("pl_net_vnd") or 0

            result = _make_eval(
                ticker,
                action,
                section=section,
                eod_price=eod_close,
                status="WIN" if actual_pl_pct > 0 else "LOSS",
                pnl_percent=round(actual_pl_pct, 4),
                strategy=strategy,
                plan_type=plan_type,
            )
            result["trade_executed"] = True
            result["actual_exit_price_vnd"] = actual_exit_vnd
            result["actual_pl_pct"] = round(actual_pl_pct, 4)
            result["actual_pl_net_vnd"] = actual_pl_net
            return result

        prev_close = price_data.get("prev_close") or 0
        if prev_close > 0:
            day_change = round((eod_close - prev_close) / prev_close * 100, 2)
        elif eod_open > 0:
            day_change = round((eod_close - eod_open) / eod_open * 100, 2)
        else:
            day_change = 0.0
        avg_cost = (holding.get("avg_cost_vnd") or 0) / 1000.0 if holding else None
        if avg_cost and avg_cost > 0:
            pnl_from_entry = round((eod_close - avg_cost) / avg_cost * 100, 2)
            has_entry_data = True
        else:
            pnl_from_entry = None
            has_entry_data = False

        stop_hit = bool(stop_price) and eod_low > 0 and eod_low <= stop_price
        if stop_hit:
            logger.warning(
                "STOP_BREACHED for HOLD %s: eod_low=%.1f <= stop=%.1f",
                ticker,
                eod_low,
                stop_price,
            )

        result = _make_eval(
            ticker,
            action,
            section=section,
            eod_price=eod_close,
            stop_hit=stop_hit,
            status="STOP_BREACHED" if stop_hit else "HOLD",
            pnl_percent=pnl_from_entry,
            day_change=day_change,
            has_entry_data=has_entry_data,
            strategy=strategy,
            plan_type=plan_type,
        )
        if prev_close > 0:
            result["prev_close"] = prev_close
        return result

    if action not in ENTRY_ACTIONS:
        return _make_eval(
            ticker,
            action,
            section=section,
            eod_price=eod_close,
            status="HOLD",
            strategy=strategy,
            plan_type=plan_type,
        )

    if not entry_price or entry_price <= 0:
        return _make_eval(
            ticker,
            action,
            section=section,
            eod_price=eod_close,
            status="MISSED",
            analysis="No entry price specified",
            strategy=strategy,
            plan_type=PLAN_TYPE_SWING,
        )

    is_atr_trail = (strategy or "").upper() in ATR_TRAIL_STRATEGIES
    entry_hit = eod_low <= entry_price
    stop_hit = entry_hit and bool(stop_price) and eod_low <= stop_price
    target_hit = entry_hit and not is_atr_trail and bool(target_price) and eod_high >= target_price

    pnl_percent = round((eod_close - entry_price) / entry_price * 100, 2) if entry_hit else 0.0

    if not entry_hit:
        status = "MISSED"
    elif stop_hit:
        status = "LOSS"
    elif target_hit:
        status = "WIN"
    else:
        status = "PENDING"

    direction_correct = (eod_close > entry_price) if entry_hit else None
    stop_buffer_pct = (
        round(abs(entry_price - stop_price) / entry_price * 100, 2)
        if entry_price and stop_price and stop_price > 0
        else None
    )

    entry_gap_pct = (
        round((entry_price - eod_low) / entry_price * 100, 2)
        if entry_price and eod_low > 0
        else None
    )
    predicted_rr = (
        round((target_price - entry_price) / (entry_price - stop_price), 2)
        if entry_price and stop_price and target_price and (entry_price - stop_price) > 0
        else None
    )
    actual_max_rr = None
    if entry_price and stop_price and (entry_price - stop_price) > 0:
        risk = entry_price - stop_price
        if eod_high and eod_high > entry_price:
            actual_max_rr = round((eod_high - entry_price) / risk, 2)

    result = _make_eval(
        ticker,
        action,
        section=section,
        entry_hit=entry_hit,
        stop_hit=stop_hit,
        target_hit=target_hit,
        eod_price=eod_close,
        pnl_percent=pnl_percent,
        status=status,
        direction_correct=direction_correct,
        stop_buffer_pct=stop_buffer_pct,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        entry_gap_pct=entry_gap_pct,
        predicted_rr=predicted_rr,
        actual_max_rr=actual_max_rr,
        strategy=rec.get("strategy"),
        plan_type=PLAN_TYPE_SWING,
    )
    return result


def _make_eval(
    ticker: str,
    recommendation: str,
    *,
    section: str = "",
    entry_hit: bool = False,
    stop_hit: bool = False,
    target_hit: bool = False,
    eod_price: float = 0.0,
    pnl_percent: float | None = 0.0,
    day_change: float | None = None,
    has_entry_data: bool | None = None,
    status: str = "MISSED",
    analysis: str = "",
    direction_correct: bool | None = None,
    stop_buffer_pct: float | None = None,
    entry_price: float | None = None,
    stop_price: float | None = None,
    target_price: float | None = None,
    entry_gap_pct: float | None = None,
    predicted_rr: float | None = None,
    actual_max_rr: float | None = None,
    strategy: str | None = None,
    plan_type: str | None = None,
) -> dict:
    """Create an evaluation dict matching the Evaluation model."""
    d = {
        "ticker": ticker,
        "recommendation": recommendation,
        "section": section,
        "entry_hit": entry_hit,
        "stop_hit": stop_hit,
        "target_hit": target_hit,
        "eod_price": eod_price,
        "pnl_percent": pnl_percent,
        "day_change": day_change,
        "has_entry_data": has_entry_data,
        "status": status,
        "analysis": analysis,
        "direction_correct": direction_correct,
        "stop_buffer_pct": stop_buffer_pct,
        "strategy": strategy,
        "plan_type": plan_type,
    }
    for field_name, field_value in [
        ("entry_price", entry_price),
        ("stop_price", stop_price),
        ("target_price", target_price),
        ("entry_gap_pct", entry_gap_pct),
        ("predicted_rr", predicted_rr),
        ("actual_max_rr", actual_max_rr),
    ]:
        if field_value is not None:
            d[field_name] = field_value
    return d
