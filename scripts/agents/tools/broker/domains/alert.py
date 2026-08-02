"""Alert domain tools — register, list, remove, effectiveness."""

from datetime import date

from ...alerts import (
    AlertActionType,
    AlertCondition,
    AlertConditionLogic,
    AlertPriority,
    RecommendedAction,
)
from ..registry import ToolDomain, register_domain_tool


async def register(
    ticker: str,
    conditions: list[AlertCondition],
    recommended_action: RecommendedAction,
    rationale: str,
    condition_logic: AlertConditionLogic = "ALL",
    priority: AlertPriority = "normal",
    action_type: AlertActionType = "notify",
    entry_price: float | None = None,
    stop_price: float | None = None,
    target_price: float | None = None,
    *,
    _ctx: dict,
) -> str:
    """Register a compound price/technical alert for a ticker.

    Args:
        ticker: Stock symbol
        conditions: One or more {type, value} pairs; types/values enforced via Literal.
        recommended_action: BUY / LIMIT_BUY / TRIM / EXIT / ADD / HOLD / WATCH / STOP.
        rationale: 1-2 sentence justification; surfaces in alert feeds.
        condition_logic: ALL (every condition) or ANY (first one fires).
        entry_price / stop_price / target_price: Required for EXIT/TRIM alerts.

    Returns:
        Single-line ack string: "Alert #{id} registered: ..." on success, or
        "Skipped: ..." / "Rejected: ..." / "Error: ..." / "Failed to register
        alert for {ticker}" on dedup, trailing-stop ratchet, validation, or
        DB failure paths.
    """
    from ...alerts import tool_register_alert

    source = _ctx.get("source", "unknown")
    raw_scan_date = _ctx.get("scan_date")
    scan_date: date = raw_scan_date if isinstance(raw_scan_date, date) else date.today()
    current_prices = _ctx.get("current_prices") or {}
    holdings_tickers = _ctx.get("holdings_tickers")
    active_alerts_snapshot = _ctx.get("active_alerts_snapshot")

    return await tool_register_alert(
        ticker=ticker,
        conditions=conditions,
        recommended_action=recommended_action,
        rationale=rationale,
        condition_logic=condition_logic,
        source=source,
        source_date=scan_date,
        priority=priority,
        action_type=action_type,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        current_prices=current_prices,
        holdings_tickers=holdings_tickers,
        active_alerts_snapshot=active_alerts_snapshot,
    )


async def list_active(ticker: str | None = None) -> str:
    """List active alerts. Check before creating to avoid duplicates.

    Returns:
        Multi-line prose listing each active alert with id, ticker,
        conditions joined by " AND "/" OR ", recommended_action, and
        rationale. "No active alerts." (optionally "for {ticker}") when
        none exist.
    """
    from ...alerts import tool_list_active_alerts

    return await tool_list_active_alerts(ticker)


async def remove(alert_id: int) -> str:
    """Cancel an alert that is no longer relevant.

    Returns:
        One of "Alert #{id} cancelled." (success) or
        "Alert #{id} not found or already inactive." (no-op).
    """
    from ...alerts import tool_remove_alert

    return await tool_remove_alert(alert_id)


async def get_effectiveness(days_back: int = 30) -> str:
    """Get alert-to-trade conversion metrics.

    Returns:
        Prose block starting with "Alert Effectiveness ({days_back}d):"
        followed by conversion rate, converted/total counts, and average
        P&L for converted vs non-converted alerts. "Alert effectiveness:
        {error}" on failure.
    """
    from ...alert_tracking import tool_get_alert_effectiveness

    return await tool_get_alert_effectiveness(days_back)


register_domain_tool(
    "alert.register",
    ToolDomain.ALERT,
    register,
    context_keys=(
        "source",
        "scan_date",
        "current_prices",
        "holdings_tickers",
        "active_alerts_snapshot",
    ),
    returns_hint="str — 'Alert #N registered' | 'Skipped: ...' | 'Error: ...'",
    mutates=True,
)
register_domain_tool(
    "alert.list_active",
    ToolDomain.ALERT,
    list_active,
    returns_hint="prose — active alerts or 'No active alerts.'",
)
register_domain_tool(
    "alert.remove",
    ToolDomain.ALERT,
    remove,
    returns_hint="str — 'Alert #N cancelled.' | 'not found...'",
    mutates=True,
)
register_domain_tool(
    "alert.get_effectiveness",
    ToolDomain.ALERT,
    get_effectiveness,
    returns_hint="prose — conversion rate + avg P&L",
)
