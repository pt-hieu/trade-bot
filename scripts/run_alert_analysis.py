#!/usr/bin/env python3
"""
Run alert analysis — triggered by GitHub Actions when alert fires.

Reads alert details from environment variables, runs mini LLM agent,
sends Telegram with analysis results.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from shared.env import load_env

load_env()

from shared.database import Database, close_db
from shared.observability import configure_observability
from shared.session import init_session
from shared.telegram import send_telegram

configure_observability()
init_session("alert")


async def main():
    alert_id = os.environ.get("ALERT_ID")
    ticker = os.environ.get("ALERT_TICKER", "")
    action = os.environ.get("ALERT_ACTION", "WATCH")

    if not alert_id or not ticker:
        print("Missing ALERT_ID or ALERT_TICKER")
        sys.exit(1)

    print(f"Analyzing alert #{alert_id}: {ticker}")

    try:
        async with Database():
            from shared.trading_config import init_trading_config

            await init_trading_config()
            # Fetch full alert from DB
            from shared.database import fetch_one

            alert = await fetch_one("SELECT * FROM alerts WHERE id = $1", int(alert_id))
            if not alert:
                print(f"Alert #{alert_id} not found")
                return

            alert = dict(alert)

            # Fetch alert conditions
            from shared.database import fetch_all

            cond_rows = await fetch_all(
                "SELECT * FROM alert_conditions WHERE alert_id = $1 ORDER BY sort_order",
                int(alert_id),
            )
            alert["conditions"] = [dict(c) for c in cond_rows]

            # Fetch current prices and technicals
            from datetime import datetime

            from shared.vnstock_client import fetch_history_batch, fetch_technicals_batch

            today = datetime.now().strftime("%Y-%m-%d")
            prices_raw, tech_raw = await asyncio.gather(
                fetch_history_batch([ticker], start=today, end=today),
                fetch_technicals_batch([ticker]),
            )

            prices = {}
            for sym, payload in prices_raw.items():
                records = payload.get("data", [])
                if records:
                    latest = records[-1]
                    prices[sym] = {
                        "open": latest.get("open"),
                        "high": latest.get("high"),
                        "low": latest.get("low"),
                        "close": latest.get("close"),
                        "volume": latest.get("volume"),
                    }

            technicals = {sym: tech for sym, tech in tech_raw.items() if tech}

            # Run mini agent analysis
            from agents.alert_analyst import analyze_alert as run_analysis

            analysis = await run_analysis(alert, prices, technicals)

            if analysis:
                # Build conditions summary for Telegram header
                conditions = alert.get("conditions") or []
                logic = alert.get("condition_logic", "ALL")
                if conditions:
                    cond_parts = [
                        f"{c.get('condition_type', '')} {c.get('condition_value', '')}"
                        for c in conditions
                    ]
                    cond_display = f" {logic} ".join(cond_parts)
                else:
                    cond_display = "N/A"

                msg = (
                    f"<b>Alert Analysis: {ticker} — {action}</b>\n"
                    f"Conditions [{logic}]: {cond_display}\n\n"
                    f"{analysis}"
                )
                send_telegram(msg)
                print(f"Analysis sent for {ticker}")

                # Log to alert_history
                import json

                from shared.database import execute

                await execute(
                    """INSERT INTO alert_history (alert_id, event_type, event_data)
                       VALUES ($1, 'analyzed', $2)""",
                    int(alert_id),
                    json.dumps({"analysis": analysis[:500]}),
                )

                # SWI-NN: close the WATCH→BUY loop. When a conditional_watch
                # alert fires, write a BUY row into daily_recommendations so
                # downstream renderers + portfolio analytics see the upgraded
                # action without waiting for the next morning scan.
                await _emit_buy_from_conditional_alert(alert, prices, technicals)
            else:
                print("No analysis produced")
    finally:
        await close_db()


async def _emit_buy_from_conditional_alert(alert: dict, prices: dict, technicals: dict) -> None:
    """Insert a BUY row into daily_recommendations on a conditional_watch fire.

    Re-evaluates the recommendation gate against the *current* regime so the
    audit story stays consistent: a stale morning-time gate decision cannot
    smuggle a BUY through after the regime shifted intraday.
    """
    import logging

    if alert.get("source") != "conditional_watch":
        return
    if (alert.get("recommended_action") or "").upper() != "BUY":
        return

    ticker = (alert.get("ticker") or "").upper()
    metadata = alert.get("alert_metadata") or {}
    if isinstance(metadata, str):
        try:
            import json as _json

            metadata = _json.loads(metadata)
        except Exception:
            metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    plan_shape = (metadata.get("plan_shape") or "").upper() or None

    # Re-evaluate the gate at trigger time. Failure to import or compute a
    # gate must NOT silently bypass — log and skip the BUY emit.
    gate_passes = False
    gate_floor: float | None = None
    try:
        from datetime import date as _date

        from agents.tools.portfolio import get_cash_balance_async
        from agents.trading_mode import determine_mode
        from pipeline.helpers.rules import extract_risk_regime, reconcile_regimes
        from shared.neon import get_macro_metrics, get_market_regime
        from shared.rules.macro_stress import classify_underlying_stress
        from shared.rules.recommendation_gate import compose_recommendation_gate

        scan_date = _date.today()

        # SWI-271: re-evaluate against the LIVE intraday regime/mode rather
        # than hardcoded NORMAL/NEUTRAL/NEUTRAL. Mirrors the pipeline live
        # derivation (phase_resume + derive.py): raw market regime reconciled
        # against the macro-derived global risk regime, trading mode from
        # deployable cash. Fail-closed: unavailable macro → CAUTIOUS via
        # extract_risk_regime, and any fetch error drops to the except below
        # (refuses to emit the BUY).
        regime_data, macro_metrics, cash_data = await asyncio.gather(
            get_market_regime(scan_date),
            get_macro_metrics(scan_date),
            get_cash_balance_async(),
        )
        macro = (
            macro_metrics
            if isinstance(macro_metrics, dict) and "error" not in macro_metrics
            else None
        )
        raw_regime = (
            regime_data.get("regime")
            if isinstance(regime_data, dict) and "error" not in regime_data
            else None
        )
        global_risk_regime = extract_risk_regime(macro)
        market_regime = (
            reconcile_regimes(raw_regime, global_risk_regime) if raw_regime else global_risk_regime
        )
        trading_mode = determine_mode((cash_data or {}).get("deployable") or 0)

        gate = compose_recommendation_gate(
            trading_mode=trading_mode,
            market_regime=market_regime,
            global_risk_regime=global_risk_regime,
            urgency_tier="DETERMINED",
            urgency_min_rr=3.5,
            urgency_max_picks=3,
            underlying_stress=classify_underlying_stress(macro),
        )
        gate_passes = bool(gate.entries_allowed)
        gate_floor = float(gate.effective_rr_floor)
    except Exception as gate_exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "[alert_buy] gate re-evaluation failed for %s: %s — refusing to emit BUY",
            ticker,
            gate_exc,
        )
        return

    if not gate_passes:
        logging.getLogger(__name__).warning(
            "[alert_buy] gate blocks BUY for %s — alert_id=%s plan_shape=%s",
            ticker,
            alert.get("id"),
            plan_shape,
        )
        return

    triggered_price = None
    px = (prices or {}).get(ticker) or {}
    triggered_price = px.get("close") or alert.get("entry_price")

    # SWI-NN: plan_shape on a BUY row always violates
    # daily_recs_plan_shape_action_chk. Run the rule + carry the original
    # shape lineage via `verdict` so audit trails preserve the WATCH→BUY
    # geometry without poisoning the CHECK.
    from shared.rules.plan_shape import coerce_plan_shape_for_check

    coerced_shape = coerce_plan_shape_for_check(plan_shape, "BUY", None, strict=False)

    rec = {
        "ticker": ticker,
        "action": "BUY",
        "section": "TOP_PICKS",
        "entry_price": triggered_price,
        "stop_price": alert.get("stop_price"),
        "target_price": alert.get("target_price"),
        "rationale": (
            f"Conditional WATCH triggered ({plan_shape or 'unknown shape'}) — "
            f"price={triggered_price}"
        ),
        "source": "alert_fire",
        "urgency": "HIGH",
        "plan_type": "SWING",
        "plan_shape": coerced_shape,
        "verdict": f"alert_fired_from={plan_shape or 'unknown'}",
        "gate_floor_at_build": gate_floor,
        "gate_passes_at_build": True,
    }

    try:
        from shared.database import fetch_val
        from shared.neon.insert_records import insert_alert_fire_recommendation
        from shared.vn_universe import VNUniverseUnavailable, load_vn_universe_async

        # Resolve / create daily_records row for today.
        record_id = await fetch_val(
            "SELECT id FROM daily_records WHERE record_date = $1", scan_date
        )
        if not record_id:
            record_id = await fetch_val(
                """
                INSERT INTO daily_records (record_date)
                VALUES ($1)
                ON CONFLICT (record_date) DO UPDATE SET record_date = EXCLUDED.record_date
                RETURNING id
                """,
                scan_date,
            )

        try:
            vn_universe = await load_vn_universe_async()
        except VNUniverseUnavailable:
            vn_universe = None

        inserted = await insert_alert_fire_recommendation(int(record_id), rec, vn_universe)
        if not inserted:
            logging.getLogger(__name__).warning(
                "[alert_buy] alert_fire insert rejected ticker=%s — skipping", ticker
            )
            return
        print(f"  [alert_buy] inserted BUY for {ticker} (record_id={record_id})")
    except Exception as insert_exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "[alert_buy] insert failed for %s: %s", ticker, insert_exc
        )


if __name__ == "__main__":
    asyncio.run(main())
