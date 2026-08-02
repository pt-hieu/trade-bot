"""Alert registration tools for the alert registrar agent."""

from datetime import date, datetime, timedelta, timezone
from typing import Literal, TypedDict

from shared.neon.alerts import (
    get_active_alerts,
)
from shared.neon.alerts import (
    register_alert as db_register_alert,
)

# Vietnam timezone offset
VN_TZ = timezone(timedelta(hours=7))

# EOD expiry: 14:45 VN time (after ATC auction)
_EOD_HOUR = 14
_EOD_MINUTE = 45

AlertConditionType = Literal[
    "price_below",
    "price_above",
    "rsi_below",
    "rsi_above",
    "volume_spike",
]
AlertPriority = Literal["high", "normal", "low"]
AlertActionType = Literal["notify", "notify_and_analyze"]
AlertConditionLogic = Literal["ALL", "ANY"]
RecommendedAction = Literal["BUY", "LIMIT_BUY", "TRIM", "EXIT", "ADD", "HOLD", "WATCH", "STOP"]


class AlertCondition(TypedDict):
    type: AlertConditionType
    value: float


VALID_CONDITION_TYPES = frozenset(
    {"price_below", "price_above", "rsi_below", "rsi_above", "volume_spike"}
)

VALID_ACTIONS = frozenset({"BUY", "LIMIT_BUY", "TRIM", "EXIT", "ADD", "HOLD", "WATCH", "STOP"})

# Actions that persist ~5 trading days regardless of source
# LIMIT_BUY needs time for price to pull back to support level
MULTI_DAY_ACTIONS = frozenset({"EXIT", "TRIM", "STOP", "LIMIT_BUY"})


def _round_condition_value(ctype: str, value: float | None) -> float | None:
    """Round condition values to sane precision. Casts numpy types (CLAUDE.md #16).

    Returns None when `value` is None so callers can pass through missing
    values without crashing on float() coercion.
    """
    if value is None:
        return None
    v = float(value)
    if ctype in ("price_below", "price_above"):
        return round(v, 0)
    if ctype in ("rsi_below", "rsi_above"):
        return round(v, 1)
    return round(v, 2)


def default_expiry(
    source: str,
    priority: str,
    source_date: date,
    recommended_action: str | None = None,
) -> datetime:
    """Calculate expiry based on source, priority, and action type.

    Protective alerts (EXIT/TRIM/STOP) persist ~5 trading days regardless of source.
    Intraday entry alerts (BUY/WATCH) from morning_brief/midday expire at EOD.
    """
    eod = datetime(
        source_date.year,
        source_date.month,
        source_date.day,
        _EOD_HOUR,
        _EOD_MINUTE,
        tzinfo=VN_TZ,
    )
    # Protective alerts persist ~5 trading days regardless of source
    if recommended_action and recommended_action.upper() in MULTI_DAY_ACTIONS:
        return eod + timedelta(days=7)
    if source in ("morning_brief", "midday"):
        return eod
    # Longterm / stop-loss alerts: ~5 trading days
    return eod + timedelta(days=7)


async def tool_register_alert(
    ticker: str,
    conditions: list[AlertCondition],
    recommended_action: RecommendedAction,
    rationale: str,
    *,
    source: str,
    source_date: date,
    condition_logic: AlertConditionLogic = "ALL",
    priority: AlertPriority = "normal",
    action_type: AlertActionType = "notify",
    entry_price: float | None = None,
    stop_price: float | None = None,
    target_price: float | None = None,
    current_prices: dict[str, float] | None = None,
    holdings_tickers: set[str] | None = None,
    active_alerts_snapshot: list[dict] | None = None,
) -> str:
    """Register a compound price/technical alert for a ticker.

    Args:
        ticker: Stock ticker (e.g., TCB, FPT)
        conditions: List of condition dicts, each with "type" and "value".
            e.g. [{"type": "price_below", "value": 93000}, {"type": "rsi_below", "value": 30}]
            Types: price_below, price_above, rsi_below, rsi_above, volume_spike
        recommended_action: BUY, TRIM, EXIT, ADD, HOLD
        rationale: Why this alert matters (1-2 sentences)
        source: Injected — morning_brief, midday, etc.
        source_date: Injected — date of the analysis
        condition_logic: ALL (all must fire simultaneously) or ANY (any one fires)
        priority: high, normal, low
        action_type: notify or notify_and_analyze
        entry_price: Suggested entry price
        stop_price: Suggested stop-loss price
        target_price: Suggested target price
        current_prices: Injected — current prices by ticker for anti-instant-trigger
        holdings_tickers: Injected — set of held tickers for TRIM/EXIT/ADD validation
        active_alerts_snapshot: Injected — pre-fetched active alerts for dedup/ratchet
    """
    ticker = ticker.upper()

    if not conditions:
        return f"Error: at least one condition required for {ticker}"
    if len(conditions) > 5:
        return f"Error: max 5 conditions per alert (got {len(conditions)})"

    # Defensive: Literal enforces at schema level for LLM callers, but manual
    # callers can still pass arbitrary strings.
    if recommended_action not in VALID_ACTIONS:
        return f"Error: '{recommended_action}' not valid. Use: {', '.join(sorted(VALID_ACTIONS))}"

    # Guard against malformed condition dicts before the TypedDict-trusted round.
    for c in conditions:
        if "type" not in c or "value" not in c:
            return f"Error: condition missing 'type' or 'value' for {ticker}: {c}"

    # Round condition values to sane precision (CLAUDE.md #16 numpy cast)
    for c in conditions:
        rounded = _round_condition_value(c["type"], c["value"])
        # Skip in-place when rounding returned None (missing input) so we
        # don't introduce None into a float-typed TypedDict field.
        if rounded is not None:
            c["value"] = rounded
    entry_price = round(float(entry_price), 0) if entry_price is not None else None
    stop_price = round(float(stop_price), 0) if stop_price is not None else None
    target_price = round(float(target_price), 0) if target_price is not None else None

    # 2a. Anti-instant-trigger: reject if any price condition is already satisfied
    prices = current_prices or {}
    current = prices.get(ticker)
    if current and current > 0:
        for condition in conditions:
            condition_type = condition.get("type", "")
            condition_value = condition.get("value")
            if condition_value is None:
                continue
            threshold = float(condition_value)
            if condition_type == "price_below" and current <= threshold:
                return (
                    f"Rejected: {ticker} price {current:,.0f} already at/below "
                    f"{threshold:,.0f} — alert would trigger instantly"
                )
            if condition_type == "price_above" and current >= threshold:
                return (
                    f"Rejected: {ticker} price {current:,.0f} already at/above "
                    f"{threshold:,.0f} — alert would trigger instantly"
                )

    # Enforce required fields for EXIT/TRIM alerts
    if (
        recommended_action in ("EXIT", "TRIM")
        and entry_price is None
        and stop_price is None
        and target_price is None
    ):
        return f"Error: EXIT/TRIM alerts require stop_price or target_price for {ticker}"

    # Validate condition types
    for c in conditions:
        if c.get("type") not in VALID_CONDITION_TYPES:
            return f"Error: invalid condition type '{c.get('type')}'"

    # 3. Holdings check — TRIM/EXIT/ADD only for held tickers
    if recommended_action in ("TRIM", "EXIT", "ADD"):
        # Use injected holdings if available, otherwise fetch (fallback for manual alerts)
        if holdings_tickers is not None:
            held_tickers = holdings_tickers
        else:
            from shared.neon.portfolio import get_portfolio_holdings

            fetched_holdings = await get_portfolio_holdings()
            held_tickers = (
                {slice_row["ticker"] for slice_row in fetched_holdings}
                if fetched_holdings
                else set()
            )
        if ticker not in held_tickers:
            return f"Error: {recommended_action} rejected - {ticker} not in portfolio"

    # 4. Dedup + 5. Ratchet — use snapshot if available, else fetch (manual alerts)
    active_alerts = (
        active_alerts_snapshot if active_alerts_snapshot is not None else await get_active_alerts()
    )

    # Dedup: same ticker + action + condition type + value within 1%
    for existing in active_alerts:
        if existing["ticker"] != ticker or existing["recommended_action"] != recommended_action:
            continue
        for new_c in conditions:
            for ex_c in existing.get("conditions", []):
                if (
                    new_c["type"] == ex_c.get("condition_type")
                    and new_c.get("value") is not None
                    and ex_c.get("condition_value") is not None
                    and abs(float(new_c["value"]) - float(ex_c["condition_value"]))
                    / max(float(ex_c["condition_value"]), 1)
                    < 0.01
                ):
                    return (
                        f"Skipped: duplicate - {ticker} already has "
                        f"{new_c['type']} {ex_c['condition_value']} "
                        f"(alert #{existing['id']})"
                    )

    # Trailing stop ratchet: EXIT/TRIM price_below must not lower existing stop
    if recommended_action in ("EXIT", "TRIM"):
        new_stops = [
            float(c["value"])
            for c in conditions
            if c.get("type") == "price_below" and c.get("value")
        ]
        if new_stops:
            new_stop = min(new_stops)
            for existing in active_alerts:
                if existing["ticker"] != ticker or existing["recommended_action"] not in (
                    "EXIT",
                    "TRIM",
                ):
                    continue
                for ec in existing.get("conditions", []):
                    if ec.get("condition_type") == "price_below" and ec.get("condition_value"):
                        existing_stop = float(ec["condition_value"])
                        if new_stop < existing_stop:
                            return (
                                f"Error: trailing stop ratchet - {ticker} has stop at "
                                f"{existing_stop:,.0f}, cannot lower to {new_stop:,.0f} "
                                f"(alert #{existing['id']})"
                            )

    alert = {
        "ticker": ticker,
        "conditions": conditions,
        "condition_logic": condition_logic.upper(),
        "source": source,
        "source_date": source_date,
        "rationale": rationale,
        "recommended_action": recommended_action,
        "priority": priority,
        "action_type": action_type,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "expires_at": default_expiry(source, priority, source_date, recommended_action),
    }
    alert_id = await db_register_alert(alert)
    if alert_id > 0:
        cond_summary = " & ".join(f"{c['type']} {c.get('value', '')}" for c in conditions)
        return f"Alert #{alert_id} registered: {ticker} [{condition_logic}] {cond_summary}"
    return f"Failed to register alert for {ticker}"


async def tool_list_active_alerts(ticker: str | None = None) -> str:
    """List active alerts with compound conditions.

    Args:
        ticker: Optional ticker filter.
    """
    alerts = await get_active_alerts()
    if ticker:
        ticker = ticker.upper()
        alerts = [a for a in alerts if a["ticker"] == ticker]
    if not alerts:
        return "No active alerts." if not ticker else f"No active alerts for {ticker}."

    lines = []
    for a in alerts:
        conditions = a.get("conditions", [])
        logic = a.get("condition_logic", "ALL")
        if conditions:
            cond_parts = [
                f"{c['condition_type']} {c.get('condition_value', '')}" for c in conditions
            ]
            sep = " AND " if logic == "ALL" else " OR "
            cond_str = sep.join(cond_parts)
        else:
            cond_str = "(no conditions)"

        lines.append(
            f"#{a['id']}: {a['ticker']} [{logic}] {cond_str} "
            f"({a['priority']}) - {a['recommended_action']}"
        )
    return "\n".join(lines)


async def tool_remove_alert(alert_id: int) -> str:
    """Cancel an alert that is no longer relevant.

    Args:
        alert_id: ID of the alert to cancel.
    """
    from shared.database import get_db

    db = await get_db()
    result = await db.execute(
        "UPDATE alerts SET status = 'cancelled', updated_at = NOW() WHERE id = $1 AND status = 'active'",
        alert_id,
    )
    count = int(result.split()[-1]) if result else 0
    return (
        f"Alert #{alert_id} cancelled."
        if count
        else f"Alert #{alert_id} not found or already inactive."
    )
