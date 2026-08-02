"""Insert functions for market data (regime, macro, foreign flow, rotation)."""

import re
from datetime import date, datetime

from shared.observability import log_info

from ..database import get_db
from ._sync import make_sync
from ._utils import json_for_jsonb_cast
from .watchlist import ensure_stock_exists


async def insert_market_regime(
    scan_date: date, data: dict, vnindex_technicals: dict | None = None
) -> bool:
    """Insert market regime classification with optional VN-Index price data."""
    db = await get_db()
    try:
        vnindex_close = None
        vnindex_change_pct = None
        if vnindex_technicals and "error" not in vnindex_technicals:
            close = vnindex_technicals.get("close")
            if close is not None:
                vnindex_close = float(close)
            change_pct = vnindex_technicals.get("change_pct")
            if change_pct is not None:
                vnindex_change_pct = float(change_pct)

        await db.execute(
            """
            INSERT INTO market_regimes (scan_date, regime, regime_confidence, key_signal, recommendation,
                                        vn_index_value, vn_index_change_pct)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (scan_date) DO UPDATE SET
                regime = EXCLUDED.regime, regime_confidence = EXCLUDED.regime_confidence,
                key_signal = EXCLUDED.key_signal, recommendation = EXCLUDED.recommendation,
                vn_index_value = EXCLUDED.vn_index_value,
                vn_index_change_pct = EXCLUDED.vn_index_change_pct
            """,
            scan_date,
            data.get("regime"),
            data.get("regime_confidence"),
            data.get("key_signal"),
            data.get("recommendation"),
            vnindex_close,
            vnindex_change_pct,
        )
        return True
    except Exception as e:
        print(f"  [Neon] Failed to insert market regime: {e}")
        return False


async def insert_macro_metrics(scan_date: date, data: dict) -> bool:
    """Insert global macro metrics and events (including commodities + yields from migration 078)."""
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO macro_metrics (
                scan_date, dxy_value, dxy_change_pct, dxy_signal_value,
                vix_value, vix_change_pct, vix_signal_value,
                usd_vnd_rate, usd_vnd_signal_value, global_risk_regime, interpretation,
                copper_price, copper_change_pct,
                oil_price, oil_change_pct,
                us_10y_yield, us_10y_change_pct,
                shanghai_close, shanghai_change_pct,
                usd_vnd_source, usd_vnd_spread,
                sp500_close, sp500_change_pct,
                nasdaq_close, nasdaq_change_pct,
                dow_close, dow_change_pct,
                breadth_advance, breadth_decline, breadth_ratio,
                geopolitical_shock
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21,
                    $22, $23, $24, $25, $26, $27, $28, $29, $30, $31::jsonb)
            ON CONFLICT (scan_date) DO UPDATE SET
                dxy_value = EXCLUDED.dxy_value, dxy_change_pct = EXCLUDED.dxy_change_pct,
                dxy_signal_value = EXCLUDED.dxy_signal_value,
                vix_value = EXCLUDED.vix_value, vix_change_pct = EXCLUDED.vix_change_pct,
                vix_signal_value = EXCLUDED.vix_signal_value,
                usd_vnd_rate = EXCLUDED.usd_vnd_rate,
                usd_vnd_signal_value = EXCLUDED.usd_vnd_signal_value,
                global_risk_regime = EXCLUDED.global_risk_regime,
                interpretation = EXCLUDED.interpretation,
                copper_price = EXCLUDED.copper_price,
                copper_change_pct = EXCLUDED.copper_change_pct,
                oil_price = EXCLUDED.oil_price,
                oil_change_pct = EXCLUDED.oil_change_pct,
                us_10y_yield = EXCLUDED.us_10y_yield,
                us_10y_change_pct = EXCLUDED.us_10y_change_pct,
                shanghai_close = EXCLUDED.shanghai_close,
                shanghai_change_pct = EXCLUDED.shanghai_change_pct,
                usd_vnd_source = EXCLUDED.usd_vnd_source,
                usd_vnd_spread = EXCLUDED.usd_vnd_spread,
                sp500_close = EXCLUDED.sp500_close,
                sp500_change_pct = EXCLUDED.sp500_change_pct,
                nasdaq_close = EXCLUDED.nasdaq_close,
                nasdaq_change_pct = EXCLUDED.nasdaq_change_pct,
                dow_close = EXCLUDED.dow_close,
                dow_change_pct = EXCLUDED.dow_change_pct,
                breadth_advance = EXCLUDED.breadth_advance,
                breadth_decline = EXCLUDED.breadth_decline,
                breadth_ratio = EXCLUDED.breadth_ratio,
                geopolitical_shock = EXCLUDED.geopolitical_shock
            """,
            scan_date,
            data.get("dxy_value"),
            data.get("dxy_change_pct"),
            data.get("dxy_signal"),
            data.get("vix_value"),
            data.get("vix_change_pct"),
            data.get("vix_signal"),
            data.get("usd_vnd_rate"),
            data.get("usd_vnd_signal"),
            data.get("global_risk_regime"),
            data.get("interpretation"),
            data.get("copper_price"),
            data.get("copper_change_pct"),
            data.get("oil_price"),
            data.get("oil_change_pct"),
            data.get("us_10y_yield"),
            data.get("us_10y_change_pct"),
            data.get("shanghai_close"),
            data.get("shanghai_change_pct"),
            data.get("usd_vnd_source"),
            data.get("usd_vnd_spread"),
            data.get("sp500_close"),
            data.get("sp500_change_pct"),
            data.get("nasdaq_close"),
            data.get("nasdaq_change_pct"),
            data.get("dow_close"),
            data.get("dow_change_pct"),
            data.get("breadth_advance"),
            data.get("breadth_decline"),
            data.get("breadth_ratio"),
            json_for_jsonb_cast(data.get("geopolitical_shock")),
        )

        await db.execute("DELETE FROM macro_events WHERE scan_date = $1", scan_date)

        for event in data.get("upcoming_events", []):
            match = re.match(r"(.+?)\s*-\s*(.+)", event)
            if match:
                event_name = match.group(1).strip()
                event_date_str = match.group(2).strip()
                try:
                    event_date = datetime.strptime(event_date_str, "%b %d, %Y").date()
                except Exception:
                    event_date = None
                await db.execute(
                    "INSERT INTO macro_events (scan_date, event_name, event_date) VALUES ($1, $2, $3)",
                    scan_date,
                    event_name,
                    event_date,
                )

        geo = data.get("geopolitical_shock") or {}
        factors = list(geo.get("catalyst_factors") or []) or None
        log_info(
            "geo_shock_persisted",
            scan_date=str(scan_date),
            shock_present=bool(geo),
            shock_factors=factors,
            regime=data.get("global_risk_regime"),
            phase_name=geo.get("phase_name") if geo else None,
            catalyst_key=geo.get("catalyst_key") if geo else None,
        )

        return True
    except Exception as e:
        print(f"  [Neon] Failed to insert macro metrics: {e}")
        return False


async def insert_foreign_flow(scan_date: date, data: dict) -> bool:
    """Insert foreign flow data with top bought/sold details."""
    db = await get_db()

    if "data" in data:
        data = data["data"]

    try:
        flow_id = await db.fetch_val(
            """
            INSERT INTO foreign_flows (scan_date, net_value_billion, buy_value_billion, sell_value_billion, signal, pattern, interpretation)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (scan_date) DO UPDATE SET
                net_value_billion = EXCLUDED.net_value_billion, buy_value_billion = EXCLUDED.buy_value_billion,
                sell_value_billion = EXCLUDED.sell_value_billion, signal = EXCLUDED.signal,
                pattern = EXCLUDED.pattern, interpretation = EXCLUDED.interpretation
            RETURNING id
            """,
            scan_date,
            data.get("net_value_billion"),
            data.get("buy_value_billion"),
            data.get("sell_value_billion"),
            data.get("signal"),
            data.get("pattern"),
            data.get("interpretation"),
        )

        await db.execute("DELETE FROM foreign_flow_details WHERE flow_id = $1", flow_id)

        async def _insert_detail(flow_id, ticker, value_billion, flow_type, rank, item):
            """Insert a flow detail row, handling bigint remaining_room."""
            await ensure_stock_exists(ticker)
            room = item.get("remaining_room")
            await db.execute(
                """INSERT INTO foreign_flow_details
                    (flow_id, ticker, value_billion, flow_type, rank,
                     buy_value_billion, sell_value_billion, net_value_billion, ownership_pct)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                flow_id,
                ticker,
                value_billion,
                flow_type,
                rank,
                item.get("buy_value_billion"),
                item.get("sell_value_billion"),
                item.get("net_value_billion"),
                item.get("ownership_pct"),
            )
            if room is not None:
                await db.execute(
                    f"""UPDATE foreign_flow_details
                    SET remaining_room = {int(room)}
                    WHERE flow_id = $1 AND ticker = $2 AND flow_type = $3""",
                    flow_id,
                    ticker,
                    flow_type,
                )

        for rank, item in enumerate(data.get("top_bought", []), 1):
            ticker = item.get("ticker")
            if ticker:
                await _insert_detail(
                    flow_id, ticker, item.get("value_billion"), "bought", rank, item
                )

        for rank, item in enumerate(data.get("top_sold", []), 1):
            ticker = item.get("ticker")
            if ticker:
                await _insert_detail(flow_id, ticker, item.get("value_billion"), "sold", rank, item)

        for item in data.get("holding_details", []):
            ticker = item.get("ticker")
            if ticker:
                await _insert_detail(
                    flow_id,
                    ticker,
                    abs(item.get("net_value_billion", 0)),
                    "holding",
                    0,
                    item,
                )

        return True
    except Exception as e:
        print(f"  [Neon] Failed to insert foreign flow: {e}")
        return False


async def insert_sector_rotation(scan_date: date, data: dict) -> bool:
    """Insert sector rotation analysis."""
    db = await get_db()

    try:
        await db.execute(
            "INSERT INTO daily_scans (scan_date, status) VALUES ($1, 'pending') ON CONFLICT (scan_date) DO NOTHING",
            scan_date,
        )

        rotation_id = await db.fetch_val(
            """
            INSERT INTO sector_rotations (scan_date, market_regime, market_avg_return, rotation_signal, reasoning)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (scan_date) DO UPDATE SET
                market_regime = EXCLUDED.market_regime, market_avg_return = EXCLUDED.market_avg_return,
                rotation_signal = EXCLUDED.rotation_signal, reasoning = EXCLUDED.reasoning
            RETURNING id
            """,
            scan_date,
            data.get("market_regime"),
            data.get("market_avg_return"),
            data.get("rotation_signal") or data.get("signal"),
            data.get("reasoning"),
        )

        await db.execute("DELETE FROM sector_rotation_details WHERE rotation_id = $1", rotation_id)

        for sector_name in data.get("hot_sectors", []):
            sector_key = sector_name.lower().replace(" ", "_").replace("-", "_")
            sector_id = await db.fetch_val("SELECT id FROM sectors WHERE name = $1", sector_key)
            if sector_id:
                sector_return = data.get("sector_returns", {}).get(sector_name)
                await db.execute(
                    "INSERT INTO sector_rotation_details (rotation_id, sector_id, classification, return_pct) VALUES ($1, $2, 'hot', $3)",
                    rotation_id,
                    sector_id,
                    sector_return,
                )

        for sector_name in data.get("cold_sectors", []):
            sector_key = sector_name.lower().replace(" ", "_").replace("-", "_")
            sector_id = await db.fetch_val("SELECT id FROM sectors WHERE name = $1", sector_key)
            if sector_id:
                sector_return = data.get("sector_returns", {}).get(sector_name)
                await db.execute(
                    "INSERT INTO sector_rotation_details (rotation_id, sector_id, classification, return_pct) VALUES ($1, $2, 'cold', $3)",
                    rotation_id,
                    sector_id,
                    sector_return,
                )

        return True
    except Exception as e:
        print(f"  [Neon] Failed to insert sector rotation: {e}")
        return False


# ============================================================================
# Sync Wrappers
# ============================================================================

insert_market_regime_sync = make_sync(insert_market_regime)
insert_macro_metrics_sync = make_sync(insert_macro_metrics)
insert_foreign_flow_sync = make_sync(insert_foreign_flow)
insert_sector_rotation_sync = make_sync(insert_sector_rotation)
