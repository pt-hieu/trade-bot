"""Alert conflict resolution and immediate position directives.

Handles BUY vs TRIM/EXIT conflicts (defensive wins) and urgent Telegram notifications.
"""

import logging
from datetime import UTC, date, datetime

from shared.config import VIETNAM_TZ
from shared.neon.alerts import get_active_alerts
from shared.rules.settlement import get_settled_shares_by_ticker, is_sellable

logger = logging.getLogger(__name__)

# Weight above which a TRIM recommendation escalates to immediate notification
CONCENTRATION_WARN_PCT = 25.0


async def send_immediate_position_directives(
    position_alerts: dict | list,
    holdings: list[dict] | None = None,
    scan_date: date | None = None,
) -> set[str]:
    """Send urgent TRIM/EXIT directives via Telegram immediately.

    These are time-based actions ("at market open"), not price triggers.
    Also escalates concentrated TRIM positions (>25% ticker weight) even when
    not marked urgent. ``holdings`` is the list[HoldingData] returned by
    ``get_portfolio_holdings`` — ticker-wide concentration sums slices.

    T+2 settlement guard: TRIM/EXIT directives are suppressed for tickers
    whose shares aren't yet sellable (bought today or 1 trading day ago).
    """
    from shared.telegram import send_telegram

    alerts = (
        position_alerts.get("alerts", []) if isinstance(position_alerts, dict) else position_alerts
    )
    if not alerts:
        return set()

    today_vn = scan_date or datetime.now(VIETNAM_TZ).date()
    settled = await get_settled_shares_by_ticker(today_vn)

    urgent = [
        alert
        for alert in alerts
        if alert.get("ticker")
        and alert.get("urgency") == "high"
        and (alert.get("action") or "").upper() in ("TRIM", "EXIT")
        and is_sellable(alert["ticker"], settled)
    ]

    # Check for concentrated TRIM positions — even if not "urgent"
    urgent_tickers = {alert.get("ticker") for alert in urgent}
    ticker_total_weight: dict[str, float] = {}
    if holdings:
        for slice_row in holdings:
            ticker = slice_row.get("ticker") or ""
            if not ticker:
                continue
            # ticker_weight_pct is identical across slices of a ticker, but sum
            # slice_weight_pct to stay robust to stale upstream data.
            ticker_total_weight[ticker] = ticker_total_weight.get(ticker, 0.0) + (
                slice_row.get("slice_weight_pct") or 0.0
            )
    concentrated_trims: list[tuple[dict, float]] = []
    if ticker_total_weight:
        for alert in alerts:
            ticker = alert.get("ticker") or ""
            action = (alert.get("action") or "").upper()
            if (
                action == "TRIM"
                and ticker in ticker_total_weight
                and ticker not in urgent_tickers
                and is_sellable(ticker, settled)
            ):
                weight = ticker_total_weight[ticker]
                if weight > CONCENTRATION_WARN_PCT:
                    concentrated_trims.append((alert, weight))

    if not urgent and not concentrated_trims:
        return set()

    lines = ["<b>ACTION REQUIRED — Open Position Directives</b>"]
    for alert in urgent:
        ticker = alert.get("ticker") or "?"
        action = (alert.get("action") or "").upper()
        note = alert.get("note") or alert.get("rationale") or ""
        lines.append(f"• <b>{action} {ticker}</b>: {note}")

    if concentrated_trims:
        lines.append("")
        lines.append("<b>⚠️ CONCENTRATION WARNING — Unexecuted TRIMs</b>")
        for alert, weight in concentrated_trims:
            ticker = alert.get("ticker", "?")
            note = alert.get("note") or alert.get("reason") or ""
            lines.append(f"• <b>TRIM {ticker}</b> ({weight:.1f}% weight): {note}")

    try:
        send_telegram("\n".join(lines))
        handled = {alert["ticker"] for alert in urgent}
        handled.update(alert["ticker"] for alert, _ in concentrated_trims)
        print(f"  Sent immediate directives for: {', '.join(handled)}")
        return handled
    except Exception as exception:
        logger.warning("Telegram directive failed: %s", exception)
        return set()


async def resolve_alert_conflicts(scan_date: date) -> int:
    """Cancel BUY alerts when same ticker has TRIM/EXIT alert (defensive wins).

    Returns count of cancelled alerts.
    """
    from shared.database import get_db

    active = await get_active_alerts()
    today_alerts = [alert for alert in active if alert.get("source_date") == scan_date]

    # Group by ticker
    by_ticker: dict[str, list[dict]] = {}
    for alert in today_alerts:
        by_ticker.setdefault(alert["ticker"], []).append(alert)

    cancelled = 0
    db = await get_db()
    now = datetime.now(UTC)

    for ticker, ticker_alerts in by_ticker.items():
        actions = {alert["recommended_action"] for alert in ticker_alerts}
        has_buy = "BUY" in actions
        has_defensive = bool(actions & {"TRIM", "EXIT"})

        if has_buy and has_defensive:
            # Cancel all BUY alerts for this ticker — defensive wins
            for alert in ticker_alerts:
                if alert["recommended_action"] == "BUY":
                    await db.execute(
                        "UPDATE alerts SET status = 'cancelled', updated_at = $1 WHERE id = $2",
                        now,
                        alert["id"],
                    )
                    cancelled += 1
                    print(
                        f"  Conflict resolved: cancelled BUY #{alert['id']} {ticker} "
                        f"(TRIM/EXIT takes priority)"
                    )

    return cancelled
