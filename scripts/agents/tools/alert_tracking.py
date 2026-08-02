#!/usr/bin/env python3
"""Alert-to-trade loop tracking.

Matches triggered alerts to executed trades and computes alert effectiveness
metrics (conversion rate, avg P/L for alert-triggered vs organic trades).
"""

from datetime import date, timedelta

from shared.errors import report_caught


async def match_trades_to_alerts(scan_date: date) -> int:
    """Match today's trades to triggered alerts by ticker + date proximity.

    Updates alert_effectiveness table with match results.

    Args:
        scan_date: Date to match trades for

    Returns:
        Number of alerts matched to trades
    """
    from shared.database import get_db

    db = await get_db()

    try:
        # Load trades executed on or near scan_date (±1 day)
        date_min = scan_date - timedelta(days=1)
        date_max = scan_date + timedelta(days=1)
        trades = await db.fetch_all(
            """
            SELECT id, ticker, entry_price_vnd, exit_price_vnd, pl_pct, status
            FROM trades_calculated
            WHERE entry_date BETWEEN $1 AND $2
            """,
            date_min,
            date_max,
        )

        if not trades:
            return 0

        # Load alerts near scan_date — include all terminal statuses for matching
        # (triggered alerts are rare; most conversions come from active/cancelled alerts
        # where the user acted on the alert before it formally triggered)
        alerts = await db.fetch_all(
            """
            SELECT id, ticker, source, recommended_action, status, triggered_at
            FROM alerts
            WHERE status IN ('triggered', 'active', 'cancelled', 'expired')
              AND source_date BETWEEN $1 AND $2
            """,
            date_min,
            date_max,
        )

        if not alerts:
            return 0

        # Build lookup: ticker -> list of alerts (BUY and EXIT/STOP separated)
        buy_alerts_by_ticker: dict[str, list[dict]] = {}
        exit_alerts_by_ticker: dict[str, list[dict]] = {}
        for alert in alerts:
            ticker = alert["ticker"].upper()
            alert_dict = dict(alert)
            action = (alert.get("recommended_action") or "").upper()
            if action in ("EXIT", "TRIM", "STOP"):
                exit_alerts_by_ticker.setdefault(ticker, []).append(alert_dict)
            else:
                buy_alerts_by_ticker.setdefault(ticker, []).append(alert_dict)

        async def _record_conversion(
            alert_dict: dict, trade_id: int, ticker: str, pnl_pct: float | None
        ) -> None:
            """Record a converted alert→trade match in alert_effectiveness."""
            await db.execute(
                """
                INSERT INTO alert_effectiveness (
                    alert_id, trade_id, ticker, alert_source,
                    recommended_action, was_converted, pnl_pct, scan_date
                ) VALUES ($1, $2, $3, $4, $5, TRUE, $6, $7)
                ON CONFLICT (alert_id, trade_id) WHERE trade_id IS NOT NULL
                DO UPDATE SET pnl_pct = COALESCE(EXCLUDED.pnl_pct, alert_effectiveness.pnl_pct)
                """,
                alert_dict["id"],
                trade_id,
                ticker,
                alert_dict.get("source"),
                alert_dict.get("recommended_action"),
                pnl_pct,
                scan_date,
            )

        matched = 0
        matched_alert_ids: set[int] = set()

        for trade in trades:
            ticker = trade["ticker"].upper()
            pnl_pct = trade.get("pl_pct")

            # Match BUY/ADD alerts to trade entries
            if ticker in buy_alerts_by_ticker and trade.get("entry_price_vnd"):
                best_alert = buy_alerts_by_ticker[ticker][0]
                await _record_conversion(best_alert, trade["id"], ticker, pnl_pct)
                matched += 1
                matched_alert_ids.add(best_alert["id"])

            # Match EXIT/TRIM/STOP alerts to trade exits
            if ticker in exit_alerts_by_ticker and trade.get("exit_price_vnd"):
                best_alert = exit_alerts_by_ticker[ticker][0]
                await _record_conversion(best_alert, trade["id"], ticker, pnl_pct)
                matched += 1
                matched_alert_ids.add(best_alert["id"])

        # Record unmatched alerts as not converted
        all_alert_dicts = [
            alert_dict
            for ticker_alerts in [*buy_alerts_by_ticker.values(), *exit_alerts_by_ticker.values()]
            for alert_dict in ticker_alerts
        ]
        for alert_dict in all_alert_dicts:
            if alert_dict["id"] in matched_alert_ids:
                continue
            await db.execute(
                """
                INSERT INTO alert_effectiveness (
                    alert_id, ticker, alert_source,
                    recommended_action, was_converted, scan_date
                ) VALUES ($1, $2, $3, $4, FALSE, $5)
                ON CONFLICT (alert_id) WHERE trade_id IS NULL
                DO NOTHING
                """,
                alert_dict["id"],
                alert_dict["ticker"].upper(),
                alert_dict.get("source"),
                alert_dict.get("recommended_action"),
                scan_date,
            )

        print(f"  Alert matching: {matched} alerts matched to trades for {scan_date}")
        return matched

    except Exception as e:
        report_caught("tool.alert_tracking.match_alerts", e, scan_date=str(scan_date))
        return 0


async def compute_alert_effectiveness(days_back: int = 30) -> dict:
    """Compute alert effectiveness metrics over rolling window.

    Args:
        days_back: Days to look back (default 30)

    Returns:
        Dict with conversion_rate, avg_pnl_converted, avg_pnl_organic,
        total_alerts, converted_alerts, sample_size
    """
    from datetime import date as date_type

    from shared.database import get_db

    db = await get_db()

    cutoff = date_type.today() - timedelta(days=days_back)

    try:
        # Get ALL rows for conversion rate — not just those with pnl
        rows = await db.fetch_all(
            "SELECT was_converted, pnl_pct FROM alert_effectiveness WHERE scan_date >= $1",
            cutoff,
        )

        if not rows:
            return {"error": "No effectiveness data available", "days_back": days_back}

        converted = [r for r in rows if r["was_converted"]]
        not_converted = [r for r in rows if not r["was_converted"]]

        def avg_pnl(records):
            vals = [float(r["pnl_pct"]) for r in records if r.get("pnl_pct") is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        conversion_rate = len(converted) / len(rows) if rows else 0.0

        return {
            "days_back": days_back,
            "total_alerts": len(rows),
            "converted_alerts": len(converted),
            "conversion_rate": round(conversion_rate, 2),
            "avg_pnl_converted": avg_pnl(converted),
            "avg_pnl_not_converted": avg_pnl(not_converted),
        }

    except Exception as e:
        return {"error": str(e), "days_back": days_back}


async def tool_get_alert_effectiveness(days_back: int = 30) -> str:
    """Get alert-to-trade conversion metrics over rolling window.

    Shows how effectively alerts translate into actual trades and their P/L impact.

    Args:
        days_back: Days to look back (default 30)
    """
    import logging

    logger = logging.getLogger(__name__)
    try:
        data = await compute_alert_effectiveness(days_back)

        if data.get("error"):
            return f"Alert effectiveness: {data['error']}"

        total = data.get("total_alerts") or 0
        converted = data.get("converted_alerts") or 0
        rate = data.get("conversion_rate") or 0
        avg_pnl_converted = data.get("avg_pnl_converted")
        avg_pnl_not_converted = data.get("avg_pnl_not_converted")

        parts = [f"Alert Effectiveness ({days_back}d):"]
        parts.append(f"  Conversion rate: {rate:.0%} ({converted}/{total} alerts → trades)")

        if avg_pnl_converted is not None:
            parts.append(f"  Avg P/L (alert-triggered): {avg_pnl_converted:+.1f}%")
        if avg_pnl_not_converted is not None:
            parts.append(f"  Avg P/L (not converted): {avg_pnl_not_converted:+.1f}%")

        if avg_pnl_converted is not None and avg_pnl_not_converted is not None:
            edge = avg_pnl_converted - avg_pnl_not_converted
            if edge > 0:
                parts.append(f"  Alert edge: +{edge:.1f}pp (alerts outperform)")
            else:
                parts.append(f"  Alert edge: {edge:.1f}pp (alerts underperform)")

        return "\n".join(parts)
    except Exception as e:
        logger.warning("tool_get_alert_effectiveness failed: %s", e)
        return f"Alert effectiveness unavailable: {e}"
