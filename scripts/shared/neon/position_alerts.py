"""Structured morning position alerts for midday handoff."""

import json
import re
from datetime import date

from ..database import get_db
from ._utils import safe_float


def _parse_price(val) -> float | None:
    """Convert LLM price strings like '93k', '115.5k', '30000' to float or None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().lower().replace(",", "")
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*k$", s)
    if m:
        return float(m.group(1)) * 1000
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _coerce_smallint(val) -> int | None:
    """Round-trip int for SMALLINT column. Returns None for missing/invalid."""
    if val is None:
        return None
    try:
        ivalue = int(val)
    except (TypeError, ValueError):
        return None
    if ivalue < 0 or ivalue > 32767:
        return None
    return ivalue


def _parse_pct(val) -> float | None:
    """Convert LLM percentage strings like '+16.4%', '-4.1%' to float or None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("%", "").replace("+", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


async def insert_morning_position_alerts(
    scan_date: date,
    alerts: list[dict],
) -> int:
    """Upsert position alerts from morning brief into morning_position_alerts table.

    Args:
        scan_date: Trading date
        alerts: List of alert dicts from position monitor ensemble output

    Returns:
        Number of rows upserted.
    """
    if not alerts:
        return 0

    db = await get_db()
    count = 0

    for alert in alerts:
        ticker = alert.get("ticker", "")
        action = alert.get("action", "HOLD")
        urgency = alert.get("urgency", "low")
        if not ticker:
            continue

        try:
            await db.execute(
                """
                INSERT INTO morning_position_alerts (
                    scan_date, ticker, action, urgency, reason,
                    target_price, stop_price, consensus, dissenting_views,
                    entry_price, pct_from_entry, weight_pct, volume_signal,
                    coverage_responding, coverage_total
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (scan_date, ticker) DO UPDATE SET
                    action = EXCLUDED.action,
                    urgency = EXCLUDED.urgency,
                    reason = EXCLUDED.reason,
                    target_price = EXCLUDED.target_price,
                    stop_price = EXCLUDED.stop_price,
                    consensus = EXCLUDED.consensus,
                    dissenting_views = EXCLUDED.dissenting_views,
                    entry_price = EXCLUDED.entry_price,
                    pct_from_entry = EXCLUDED.pct_from_entry,
                    weight_pct = EXCLUDED.weight_pct,
                    volume_signal = EXCLUDED.volume_signal,
                    coverage_responding = EXCLUDED.coverage_responding,
                    coverage_total = EXCLUDED.coverage_total,
                    created_at = NOW()
                """,
                scan_date,
                ticker,
                action[:10],
                urgency[:10],
                alert.get("reason", ""),
                _parse_price(alert.get("target")),
                _parse_price(alert.get("stop")),
                alert.get("consensus"),
                json.dumps(alert.get("dissenting_views", [])),
                _parse_price(alert.get("entry_price")),
                _parse_pct(alert.get("pct_from_entry")),
                _parse_pct(alert.get("weight_pct")),
                alert.get("volume_signal"),
                _coerce_smallint(alert.get("coverage_responding")),
                _coerce_smallint(alert.get("coverage_total")),
            )
            count += 1
        except Exception as e:
            print(f"  [Neon] Failed to insert position alert {ticker}: {e}")

    return count


async def get_morning_position_alerts(scan_date: date) -> list[dict]:
    """Load structured position alerts for a trading date.

    Args:
        scan_date: Trading date to query

    Returns:
        List of alert dicts, empty if none found.
    """
    db = await get_db()

    try:
        rows = await db.fetch_all(
            """
            SELECT
                ticker, action, urgency, reason,
                target_price, stop_price, consensus, dissenting_views,
                entry_price, pct_from_entry, weight_pct, volume_signal,
                coverage_responding, coverage_total
            FROM morning_position_alerts
            WHERE scan_date = $1
            ORDER BY
                CASE urgency WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                ticker
            """,
            scan_date,
        )
    except Exception as e:
        print(f"  [Neon] Failed to load position alerts for {scan_date}: {e}")
        return []

    results = []
    for row in rows:
        dissenting = row["dissenting_views"]
        if isinstance(dissenting, str):
            try:
                dissenting = json.loads(dissenting)
            except Exception:
                dissenting = []

        results.append(
            {
                "ticker": row["ticker"],
                "action": row["action"],
                "urgency": row["urgency"],
                "reason": row["reason"],
                "target_price": safe_float(row["target_price"]),
                "stop_price": safe_float(row["stop_price"]),
                "consensus": row["consensus"],
                "dissenting_views": dissenting,
                "entry_price": safe_float(row["entry_price"]),
                "pct_from_entry": safe_float(row["pct_from_entry"]),
                "weight_pct": safe_float(row["weight_pct"]),
                "volume_signal": row["volume_signal"],
                "coverage_responding": row["coverage_responding"],
                "coverage_total": row["coverage_total"],
            }
        )

    return results


async def upsert_with_passthrough(scan_date: date, alerts: list[dict]) -> int:
    """Upsert alerts atomically: read prior → merge via preserve_higher_urgency → upsert.

    Sole writer for morning_position_alerts under retry conditions. Removes
    the read-then-merge-then-upsert race by performing both reads under one
    code path. The merge layer (`preserve_higher_urgency`) decides whether
    a prior higher-urgency alert wins, or whether the current higher-coverage
    attempt overrides it (`COVERAGE_GAP_OVERRIDE`).
    """
    from shared.rules.aggregator_passthrough import preserve_higher_urgency

    prior = await get_morning_position_alerts(scan_date)
    merged = preserve_higher_urgency(prior, alerts)
    return await insert_morning_position_alerts(scan_date, merged)
