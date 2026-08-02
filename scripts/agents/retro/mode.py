#!/usr/bin/env python3
"""
Trading mode compliance and counterfactual analysis.

Extracted from compute.py to stay under 300-line limit.
"""

from .won import ENTRY_ACTIONS as _ENTRY_ACTIONS


def compute_mode_compliance(
    recommendations: list[dict],
    trading_mode: str,
) -> tuple[bool, list[str]]:
    """
    Check if recommendations respected the trading mode.

    Returns:
        (is_compliant, list_of_violations)
    """
    if not trading_mode or trading_mode == "NORMAL":
        return True, []

    violations = []
    for rec in recommendations:
        action = rec.get("action", "").upper()
        ticker = rec.get("ticker", "")

        if trading_mode == "LOW_CASH" and action in _ENTRY_ACTIONS:
            violations.append(f"{action} {ticker} in LOW_CASH mode")

        if trading_mode == "REALLOCATION" and action in _ENTRY_ACTIONS:
            violations.append(f"{action} {ticker} in REALLOCATION mode")

    # REALLOCATION also needs at least one EXIT
    if trading_mode == "REALLOCATION":
        has_exit = any(rec.get("action", "").upper() in ("EXIT", "TRIM") for rec in recommendations)
        if not has_exit:
            violations.append("No EXIT recommendations in REALLOCATION mode")

    return len(violations) == 0, violations


def compute_mode_counterfactual(
    evaluations: list[dict],
    trading_mode: str,
    eod_prices: dict,
) -> dict:
    """
    What would have happened if trading mode hadn't blocked entries?

    Looks at EXCLUDED tickers (SKIP/AVOID/WAIT/WATCH) and measures
    their actual day change — counterfactual for mode effectiveness.
    """
    if trading_mode == "NORMAL":
        return {"blocked_trades": [], "net_impact": "0%", "mode_was_correct": True}

    blocked = []
    for e in evaluations:
        if e["status"] == "EXCLUDED":
            ticker = e["ticker"]
            price_data = eod_prices.get(ticker, {})
            if not price_data or "error" in price_data:
                continue
            open_p = price_data.get("open", 0)
            close_p = price_data.get("close", 0)
            if open_p > 0:
                day_change = round((close_p - open_p) / open_p * 100, 2)
                blocked.append(
                    {
                        "ticker": ticker,
                        "action_blocked": e["recommendation"],
                        "day_change_pct": day_change,
                        "would_win": day_change > 0,
                    }
                )

    if not blocked:
        return {"blocked_trades": [], "net_impact": "0%", "mode_was_correct": True}

    wins = sum(1 for b in blocked if b["would_win"])
    losses = len(blocked) - wins
    net = sum(b["day_change_pct"] for b in blocked)
    return {
        "blocked_trades": blocked,
        "blocked_wins": wins,
        "blocked_losses": losses,
        "net_impact": f"{net:+.1f}%",
        "mode_was_correct": losses >= wins,
    }
