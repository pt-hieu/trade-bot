"""Deterministic alert registration — multi-tranche dip-buy from sell-off detector."""

import uuid
from datetime import date

from agents.tools.alerts import default_expiry
from shared.neon.alerts import register_alert as db_register_alert
from shared.rules.entry_gates import RiskRegime, TradingMode

from .deterministic import _build_alert_metadata, _is_already_triggered


async def register_dip_buy_alerts(
    selloff_setups: list[dict],
    source: str,
    scan_date: date,
    risk_regime: RiskRegime = "CALM",
    trading_mode: TradingMode = "NORMAL",
    current_prices: dict[str, float] | None = None,
) -> int:
    """Register multi-tranche dip-buy alerts from sell-off detector output."""
    if risk_regime == "CRISIS":
        print(f"  Skipping dip-buy alerts: risk_regime={risk_regime}")
        return 0

    prices = current_prices or {}
    count = 0
    for setup in selloff_setups:
        ticker = setup.get("ticker") or ""
        pick = setup.get("pick", {})
        tranche_zones = setup.get("tranche_zones", [])
        setup_type = setup.get("classification") or "UNKNOWN"
        conviction = setup.get("conviction") or "LOW"
        volume_ratio = (setup.get("volume_profile") or {}).get("ratio", 0)
        rsi = setup.get("rsi", 50)
        foreign_net_billion = setup.get("foreign_net_b")

        if not ticker or not tranche_zones:
            continue

        # Shared setup_id links all tranches for this setup
        setup_id = str(uuid.uuid4())
        total_tranches = len(tranche_zones)

        raw_stop = pick.get("stop") or pick.get("stop_price")
        raw_target = pick.get("target") or pick.get("target_price")
        stop = round(float(raw_stop), 0) if raw_stop else None
        target = round(float(raw_target), 0) if raw_target else None

        foreign_str = (
            f", foreign {foreign_net_billion:+.0f}B VND" if foreign_net_billion is not None else ""
        )
        base_rationale = (
            f"{ticker} {setup_type} ({conviction}): "
            f"{setup.get('consecutive_red_days', 0)} red days, "
            f"vol {volume_ratio:.1f}x avg, RSI {rsi:.0f}{foreign_str}"
        )

        for zone in tranche_zones:
            zone_number = zone["zone"]
            zone_price = round(float(zone["price"]), 0)
            percent_of_size = zone["pct_of_size"]
            zone_rationale = zone.get("rationale") or ""

            if _is_already_triggered(ticker, zone_price, prices, f"dip-buy tranche {zone_number}"):
                continue

            alert = {
                "ticker": ticker,
                "conditions": [{"type": "price_below", "value": zone_price}],
                "condition_logic": "ALL",
                "source": "dip_buy",
                "source_date": scan_date,
                "recommended_action": "BUY",
                "action_type": "notify_and_analyze",
                "priority": "high" if conviction in ("HIGH", "MEDIUM") else "normal",
                "rationale": (
                    f"[Tranche {zone_number}/{total_tranches}, {percent_of_size}% size] "
                    f"{base_rationale} — {zone_rationale}"
                ),
                "entry_price": zone_price,
                "stop_price": stop,
                "target_price": target,
                "expires_at": default_expiry("dip_buy", "normal", scan_date, "BUY"),
                "alert_metadata": _build_alert_metadata(
                    risk_regime,
                    trading_mode,
                    extra={
                        "setup_id": setup_id,
                        "tranche": zone_number,
                        "total_tranches": total_tranches,
                        "setup_type": setup_type,
                        "pct_of_size": percent_of_size,
                        "conviction": conviction,
                    },
                ),
            }
            alert_id = await db_register_alert(alert)
            if alert_id > 0:
                count += 1
                print(
                    f"  Dip-buy alert #{alert_id}: {ticker} Tranche {zone_number}/{total_tranches} "
                    f"@ {zone_price:,.0f} ({setup_type}, {conviction})"
                )

    return count
