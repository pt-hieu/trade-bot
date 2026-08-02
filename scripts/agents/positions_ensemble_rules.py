"""
Deterministic rule functions for positions ensemble.

Pure Python functions — no agent, no async, no LLM dependencies.
"""

from __future__ import annotations

import logging

from shared.rules.max_loss import ceiling_for_plan
from shared.trading_config import get_trading_config

from .positions_ensemble_models import AnalystReport

logger = logging.getLogger(__name__)


def compute_portfolio_drawdown_context(holdings: list[dict]) -> str:
    """Classify portfolio drawdown as beta (market) vs alpha (stock-specific).

    When most positions are underwater simultaneously, this is likely market-wide
    (beta) risk rather than stock-specific (alpha) failure. Returns context string
    to inject into analyst/aggregator prompts to prevent panic-sell behavior.

    Operates per (ticker, plan_type) slice — a dual-listed ticker with one
    profitable slice and one underwater slice counts each separately, which is
    consistent with the old single-row-per-ticker behavior where only one slice
    was visible.

    Returns empty string if no broad drawdown detected.
    """
    stock_holdings = [
        holding
        for holding in holdings
        if isinstance(holding, dict) and (holding.get("type") or "Stock") == "Stock"
    ]
    if len(stock_holdings) < 2:
        return ""

    total = len(stock_holdings)
    underwater = [
        {
            "ticker": f"{holding['ticker']} ({holding.get('plan_type') or 'SWING'})"
            if any(h["ticker"] == holding["ticker"] and h is not holding for h in stock_holdings)
            else holding["ticker"],
            "drawdown": (holding.get("pct_from_entry") or 0),
        }
        for holding in stock_holdings
        if (holding.get("pct_from_entry") or 0) < 0
    ]
    if not underwater:
        return ""

    ratio = len(underwater) / total
    average_drawdown = sum(position["drawdown"] for position in underwater) / len(underwater)

    if ratio >= 0.5 and average_drawdown <= -3.0:
        drawdown_type = "BROAD_MARKET"
    elif ratio >= 0.5:
        drawdown_type = "MODERATE_BROAD"
    else:
        return ""

    underwater_tickers_text = ", ".join(
        f"{position['ticker']} ({position['drawdown']:+.1f}%)" for position in underwater
    )
    return (
        f"PORTFOLIO DRAWDOWN CONTEXT\n"
        f"Drawdown type: {drawdown_type}\n"
        f"Underwater: {len(underwater)}/{total} ({ratio:.0%}), avg {average_drawdown:+.1f}%\n"
        f"Tickers: {underwater_tickers_text}\n"
        f"INTERPRETATION: Likely BETA (market-wide) risk, not ALPHA (stock failure). "
        f"Evaluate on VALUE MERIT, not loss percentage alone."
    )


def enforce_concentration_limits(alerts: list[dict], holdings: list[dict]) -> list[dict]:
    """Deterministic post-LLM override for concentration and gain limits.

    Rules (per workflows.md + CLAUDE.md):
      SWING:
        - weight > 40% → force TRIM (urgency: high)
        - gain > 15%   → force TRIM (urgency: medium)
        - weight > 40% AND gain > 15% → force EXIT (urgency: high)
      LONGTERM:
        - weight > 45% → force TRIM (urgency: medium)
        - weight > 55% → force TRIM (urgency: high)
      ANY:
        - weight > 60% → force EXIT (urgency: high)

    When the deterministic rule is more aggressive than the LLM recommendation,
    override with [CONCENTRATION OVERRIDE] prefix in reason.
    Tickers present in holdings but missing from alerts get a new alert injected.
    """
    _ACTION_RANK = {"HOLD": 0, "ADD": 0, "EVALUATE": 0, "TRIM": 1, "EXIT": 2}

    def _rank(action: str) -> int:
        return _ACTION_RANK.get(action.upper(), 0)

    # Build a dict of existing alerts keyed by ticker (uppercase)
    alerts_by_ticker: dict[str, dict] = {}
    for alert in alerts:
        alerts_by_ticker[alert["ticker"].upper()] = alert

    def _apply_override(ticker: str, forced_action: str, forced_urgency: str, reason: str) -> None:
        """Apply a forced action if it's more aggressive than current alert."""
        ticker_upper = ticker.upper()
        if ticker_upper in alerts_by_ticker:
            existing = alerts_by_ticker[ticker_upper]
            if _rank(forced_action) > _rank(existing.get("action", "HOLD")):
                existing["action"] = forced_action
                existing["urgency"] = forced_urgency
                existing["reason"] = f"[CONCENTRATION OVERRIDE] {reason}"
        else:
            # Inject new alert for this ticker
            alerts_by_ticker[ticker_upper] = {
                "ticker": ticker,
                "action": forced_action,
                "urgency": forced_urgency,
                "reason": f"[CONCENTRATION OVERRIDE] {reason}",
                "target": "N/A",
                "stop": "N/A",
                "consensus": "override",
                "dissenting_views": [],
            }

    trading_config = get_trading_config()
    exit_pct = trading_config.concentration_exit_pct
    swing_trim_weight = trading_config.swing_trim_weight_pct
    swing_trim_gain = trading_config.swing_trim_gain_pct
    longterm_trim_high = trading_config.longterm_trim_weight_high_pct
    longterm_trim_medium = trading_config.longterm_trim_weight_med_pct

    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        ticker = holding.get("ticker") or ""
        if not ticker:
            continue
        plan_type = (holding.get("plan_type") or "SWING").upper()
        # Concentration gates operate on per-slice weight so SWING + LONGTERM
        # slices of the same ticker are evaluated independently.
        weight = holding.get("slice_weight_pct") or 0.0
        gain = holding.get("gain_pct") or 0.0

        # Max-loss ceiling (plan-type differentiated, checked first). Shared
        # helper keeps the rule consistent with `shared/rules/max_loss.py`
        # which midday_check reads straight off per-plan DB rows.
        loss_pct = -(holding.get("gain_pct") or 0.0)
        ceiling = ceiling_for_plan(plan_type, trading_config)
        if ceiling is not None and loss_pct > ceiling:
            _apply_override(
                ticker,
                "EXIT",
                "high",
                f"[MAX LOSS CEILING] {plan_type} loss {loss_pct:.1f}% exceeds "
                f"{ceiling:.0f}% limit (from trading_config)",
            )
            continue

        # Universal: >exit_pct% weight → EXIT regardless of plan
        if weight > exit_pct:
            _apply_override(
                ticker,
                "EXIT",
                "high",
                f"Weight {weight:.1f}% exceeds absolute {exit_pct:.0f}% concentration limit",
            )
            continue  # No need to check other rules

        if plan_type == "SWING":
            both_concentrated_and_profitable = weight > swing_trim_weight and gain > swing_trim_gain
            if both_concentrated_and_profitable:
                _apply_override(
                    ticker,
                    "EXIT",
                    "high",
                    f"SWING concentrated at {weight:.1f}% weight AND {gain:+.1f}% gain — exit to rebalance",
                )
            elif weight > swing_trim_weight:
                _apply_override(
                    ticker,
                    "TRIM",
                    "high",
                    f"SWING weight {weight:.1f}% exceeds {swing_trim_weight:.0f}% concentration limit",
                )
            elif gain > swing_trim_gain:
                _apply_override(
                    ticker,
                    "TRIM",
                    "medium",
                    f"SWING gain {gain:+.1f}% exceeds {swing_trim_gain:.0f}% profit-taking threshold",
                )

        elif plan_type == "LONGTERM":
            if weight > longterm_trim_high:
                _apply_override(
                    ticker,
                    "TRIM",
                    "high",
                    f"LONGTERM weight {weight:.1f}% far exceeds {longterm_trim_medium:.0f}% target — trim to rebalance",
                )
            elif weight > longterm_trim_medium:
                _apply_override(
                    ticker,
                    "TRIM",
                    "medium",
                    f"LONGTERM weight {weight:.1f}% exceeds {longterm_trim_medium:.0f}% concentration guideline",
                )

    return list(alerts_by_ticker.values())


def _calc_consensus(
    ticker: str,
    final_action: str,
    technical: AnalystReport,
    value: AnalystReport,
    thesis: AnalystReport,
) -> str:
    """Calculate consensus level: how many sub-agents agree with the final action.

    Returns:
        unanimous: all sub-agents agree with final action
        majority: 2+ sub-agents agree with final action
        minority_override: only 1 sub-agent agrees (LLM overrode majority)
        override: 0 sub-agents agree (full LLM override)
        no_data: no sub-agent views found for this ticker
    """
    actions = []
    for report in [technical, value, thesis]:
        for view in report.views:
            if view.ticker.upper() == ticker.upper():
                actions.append(view.action.upper())
                break

    if not actions:
        return "no_data"

    final = final_action.upper()
    agreeing = sum(1 for action in actions if action == final)

    if agreeing == len(actions):
        return "unanimous"
    if agreeing >= 2:
        return "majority"
    if agreeing == 1:
        return "minority_override"
    return "override"


def _get_dissent(
    ticker: str,
    final_action: str,
    technical: AnalystReport,
    value: AnalystReport,
    thesis: AnalystReport,
) -> list[str]:
    """Get list of dissenting views for a ticker."""
    dissent = []
    analyst_names = ["Technical", "Value", "Thesis"]
    for analyst_name, report in zip(analyst_names, [technical, value, thesis], strict=False):
        for view in report.views:
            if view.ticker.upper() == ticker.upper():
                if view.action.upper() != final_action.upper():
                    dissent.append(f"{analyst_name}: {view.action} ({view.reasoning})")
                break
    return dissent
