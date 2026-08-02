"""Market regime, sector rotation, and macro metrics queries."""

from datetime import date
from typing import TYPE_CHECKING, cast

from ..database import get_db
from ._types import MacroHistoryEntry, RegimeHistoryEntry
from ._utils import parse_jsonb_list as _parse_jsonb_list  # re-exported for callers
from ._utils import parse_jsonb_object as _parse_jsonb_dict
from ._utils import safe_float

if TYPE_CHECKING:
    from pipeline.types import GeopoliticalShockDict


async def get_market_regime(scan_date: date | None = None) -> dict:
    """Get market regime classification (RISK_ON/OFF/NEUTRAL)."""
    if scan_date is None:
        scan_date = date.today()

    db = await get_db()
    row = await db.fetch_one(
        """
        SELECT regime, regime_confidence, key_signal, recommendation
        FROM market_regimes WHERE scan_date = $1
    """,
        scan_date,
    )

    if not row:
        return {"error": f"No market regime data found for {scan_date}"}

    return {
        "regime": row["regime"],
        "regime_confidence": safe_float(row["regime_confidence"], default=0.5),
        "key_signal": row["key_signal"] or "",
        "recommendation": row["recommendation"] or "",
    }


async def get_sector_rotation(scan_date: date | None = None) -> dict:
    """Get sector rotation analysis (hot/cold sectors)."""
    if scan_date is None:
        scan_date = date.today()

    db = await get_db()
    row = await db.fetch_one(
        """
        SELECT sr.id, sr.rotation_signal, sr.market_regime
        FROM sector_rotations sr WHERE sr.scan_date = $1
    """,
        scan_date,
    )

    if not row:
        return {"error": f"No sector rotation data found for {scan_date}"}

    details = await db.fetch_all(
        """
        SELECT s.name as sector, srd.classification
        FROM sector_rotation_details srd
        JOIN sectors s ON s.id = srd.sector_id
        WHERE srd.rotation_id = $1
    """,
        row["id"],
    )

    hot_sectors = [d["sector"] for d in details if d["classification"] == "hot"]
    cold_sectors = [d["sector"] for d in details if d["classification"] == "cold"]

    # Read regime from authoritative market_regimes table, not the
    # stale sector_rotations copy (sector_rotation runs before regime is determined)
    regime_data = await get_market_regime(scan_date)
    authoritative_regime = regime_data.get("regime") if "error" not in regime_data else None

    return {
        "hot_sectors": hot_sectors,
        "cold_sectors": cold_sectors,
        "rotation_signal": row["rotation_signal"] or "",
        "market_regime": authoritative_regime or row["market_regime"] or "NEUTRAL",
    }


async def get_macro_metrics(scan_date: date | None = None) -> dict:
    """Get global macro metrics (DXY, VIX, USD/VND, risk regime)."""
    if scan_date is None:
        scan_date = date.today()

    db = await get_db()
    row = await db.fetch_one(
        """
        SELECT
            dxy_value, dxy_change_pct, dxy_signal_value,
            vix_value, vix_change_pct, vix_signal_value,
            usd_vnd_rate, usd_vnd_signal_value, global_risk_regime, interpretation,
            oil_price, oil_change_pct, copper_price, copper_change_pct,
            us_10y_yield, us_10y_change_pct, shanghai_close, shanghai_change_pct,
            usd_vnd_source, usd_vnd_spread,
            sp500_close, sp500_change_pct, nasdaq_close, nasdaq_change_pct,
            dow_close, dow_change_pct,
            breadth_advance, breadth_decline, breadth_ratio,
            geopolitical_shock
        FROM macro_metrics WHERE scan_date = $1
    """,
        scan_date,
    )

    if not row:
        return {"error": f"No macro data found for {scan_date}"}

    events_rows = await db.fetch_all(
        """
        SELECT event_name, event_date FROM macro_events WHERE scan_date = $1
    """,
        scan_date,
    )

    return {
        "dxy_value": safe_float(row["dxy_value"]),
        "dxy_change_pct": safe_float(row.get("dxy_change_pct")),
        "dxy_signal": row["dxy_signal_value"] or "NEUTRAL",
        "vix_value": safe_float(row["vix_value"]),
        "vix_change_pct": safe_float(row.get("vix_change_pct")),
        "vix_signal": row["vix_signal_value"] or "NEUTRAL",
        "usd_vnd_rate": safe_float(row["usd_vnd_rate"]),
        "usd_vnd_signal": row["usd_vnd_signal_value"] or "STABLE",
        "usd_vnd_source": row["usd_vnd_source"],
        "usd_vnd_spread": safe_float(row["usd_vnd_spread"]),
        "global_risk_regime": row["global_risk_regime"] or "CAUTIOUS",
        "interpretation": row["interpretation"],
        "upcoming_events": [e["event_name"] for e in events_rows] if events_rows else [],
        "oil_price": safe_float(row["oil_price"]),
        "oil_change_pct": safe_float(row["oil_change_pct"]),
        "copper_price": safe_float(row["copper_price"]),
        "copper_change_pct": safe_float(row["copper_change_pct"]),
        "us_10y_yield": safe_float(row["us_10y_yield"]),
        "us_10y_change_pct": safe_float(row["us_10y_change_pct"]),
        "shanghai_close": safe_float(row["shanghai_close"]),
        "shanghai_change_pct": safe_float(row["shanghai_change_pct"]),
        # US indices (migration 214)
        "sp500_close": safe_float(row.get("sp500_close")),
        "sp500_change_pct": safe_float(row.get("sp500_change_pct")),
        "nasdaq_close": safe_float(row.get("nasdaq_close")),
        "nasdaq_change_pct": safe_float(row.get("nasdaq_change_pct")),
        "dow_close": safe_float(row.get("dow_close")),
        "dow_change_pct": safe_float(row.get("dow_change_pct")),
        # Market breadth (migration 214)
        "breadth_advance": int(row["breadth_advance"])
        if row.get("breadth_advance") is not None
        else None,
        "breadth_decline": int(row["breadth_decline"])
        if row.get("breadth_decline") is not None
        else None,
        "breadth_ratio": safe_float(row.get("breadth_ratio")),
        "geopolitical_shock": cast(
            "GeopoliticalShockDict | None",
            _parse_jsonb_dict(row.get("geopolitical_shock")),
        ),
    }


async def get_regime_history(days: int = 5) -> list[RegimeHistoryEntry]:
    """Get regime history for the last N days."""
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT scan_date, regime, regime_confidence
        FROM market_regimes ORDER BY scan_date DESC LIMIT $1
    """,
        days,
    )

    return [
        {
            "date": str(row["scan_date"]),
            "regime": row["regime"],
            "confidence": float(row["regime_confidence"])
            if row["regime_confidence"] is not None
            else 0.5,
        }
        for row in rows
    ]


async def get_vn_index_trend_3d(scan_date: date | None = None) -> float | None:
    """VN-Index 3-trading-day cumulative % change, or None if <3 rows."""
    db = await get_db()
    rows = await db.fetch_all(
        "SELECT vn_index_change_pct FROM market_regimes "
        "WHERE scan_date <= $1 AND vn_index_change_pct IS NOT NULL "
        "ORDER BY scan_date DESC LIMIT 3",
        scan_date or date.today(),
    )
    if len(rows) < 3:
        return None
    return float(sum(float(row["vn_index_change_pct"]) for row in rows))


async def get_midday_check(scan_date: date | None = None) -> dict:
    """Get midday check data for a given date."""
    if scan_date is None:
        scan_date = date.today()

    db = await get_db()
    row = await db.fetch_one(
        """
        SELECT id, trading_mode, morning_reflection, afternoon_plan, capital_note,
               recommendation_overrides
        FROM midday_checks WHERE scan_date = $1
    """,
        scan_date,
    )

    if not row:
        return {"error": f"No midday check data found for {scan_date}"}

    entries_hit = await db.fetch_all(
        """
        SELECT ticker, recommended_entry_vnd, actual_low_vnd, current_price_vnd, status
        FROM midday_entries_hit WHERE midday_id = $1
    """,
        row["id"],
    )

    big_movers = await db.fetch_all(
        """
        SELECT ticker, open_price_vnd, current_price_vnd, change_pct, direction
        FROM midday_big_movers WHERE midday_id = $1
    """,
        row["id"],
    )

    position_alerts = await db.fetch_all(
        """
        SELECT ticker, current_price_vnd, level_vnd, level_type, distance_pct, urgency
        FROM midday_position_alerts WHERE midday_id = $1
    """,
        row["id"],
    )

    return {
        "trading_mode": row["trading_mode"] or "NORMAL",
        "morning_reflection": row["morning_reflection"] or "",
        "afternoon_plan": _parse_jsonb_list(row["afternoon_plan"]),
        "capital_note": row["capital_note"] or "",
        "entries_hit": [
            {
                "ticker": e["ticker"],
                "recommended_entry": e["recommended_entry_vnd"] / 1000
                if e["recommended_entry_vnd"] is not None
                else None,
                "actual_low": e["actual_low_vnd"] / 1000
                if e["actual_low_vnd"] is not None
                else None,
                "current_price": e["current_price_vnd"] / 1000
                if e["current_price_vnd"] is not None
                else None,
                "status": e["status"],
            }
            for e in entries_hit
        ],
        "big_movers": [
            {
                "ticker": m["ticker"],
                "open_price": m["open_price_vnd"] / 1000
                if m["open_price_vnd"] is not None
                else None,
                "current_price": m["current_price_vnd"] / 1000
                if m["current_price_vnd"] is not None
                else None,
                "change_pct": safe_float(m["change_pct"]),
                "direction": m["direction"],
            }
            for m in big_movers
        ],
        "position_alerts": [
            {
                "ticker": a["ticker"],
                "current_price": a["current_price_vnd"] / 1000
                if a["current_price_vnd"] is not None
                else None,
                "level": a["level_vnd"] / 1000 if a["level_vnd"] is not None else None,
                "level_type": a["level_type"],
                "distance_pct": safe_float(a["distance_pct"]),
                "urgency": a["urgency"],
            }
            for a in position_alerts
        ],
        "recommendation_overrides": _parse_jsonb_list(row["recommendation_overrides"]),
    }


async def has_upcoming_macro_events(scan_date: date, lookback_days: int = 3) -> bool:
    """Check if macro events were recorded in the last N days (proxy for upcoming events).

    macro_events.event_date is often NULL (LLM didn't parse a date), so we use
    recency of events themselves: if any events were registered in the last few days,
    something macro is happening that warrants CAUTIOUS escalation.
    """
    from datetime import timedelta

    db = await get_db()
    start_date = scan_date - timedelta(days=lookback_days)
    count = await db.fetch_val(
        "SELECT COUNT(*) FROM macro_events WHERE scan_date >= $1 AND scan_date < $2",
        start_date,
        scan_date,
    )
    return (count or 0) > 0


async def get_macro_history(days: int = 30) -> list[MacroHistoryEntry]:
    """Get macro history for the last N days (newest first).

    Default 30 days to support rolling median calculation for dynamic thresholds.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT scan_date, global_risk_regime, dxy_signal_value, vix_signal_value,
               dxy_value, vix_value, oil_price, copper_price, us_10y_yield,
               shanghai_close, usd_vnd_rate, usd_vnd_source, geopolitical_shock
        FROM macro_metrics ORDER BY scan_date DESC LIMIT $1
    """,
        days,
    )

    return [
        {
            "date": str(row["scan_date"]),
            "global_risk_regime": row["global_risk_regime"] or "CAUTIOUS",
            "dxy_signal": row["dxy_signal_value"] or "NEUTRAL",
            "vix_signal": row["vix_signal_value"] or "NEUTRAL",
            "dxy_value": safe_float(row["dxy_value"]),
            "vix_value": safe_float(row["vix_value"]),
            "oil_price": safe_float(row.get("oil_price")),
            "copper_price": safe_float(row.get("copper_price")),
            "us_10y_yield": safe_float(row.get("us_10y_yield")),
            "shanghai_close": safe_float(row.get("shanghai_close")),
            "usd_vnd_rate": safe_float(row.get("usd_vnd_rate")),
            "usd_vnd_source": row.get("usd_vnd_source"),
            "geopolitical_shock": cast(
                "GeopoliticalShockDict | None",
                _parse_jsonb_dict(row.get("geopolitical_shock")),
            ),
        }
        for row in rows
    ]
