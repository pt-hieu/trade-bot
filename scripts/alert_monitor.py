#!/usr/bin/env python3
"""
Alert Monitor Daemon — polls prices during market hours, triggers alerts.

Designed to run on Lightsail as a systemd service alongside vnstock-api.
Polls every 5 minutes during VN market hours (09:00-14:45 VN time).

Usage:
    python alert_monitor.py           # Run daemon loop
    python alert_monitor.py --once    # Single poll cycle (for testing)
"""

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta

import httpx

# Add scripts/ to path so shared modules are importable
sys.path.insert(0, os.path.dirname(__file__))
try:
    from shared.env import load_env

    load_env()
except ImportError:
    pass  # On Lightsail, env vars are set via systemd EnvironmentFile

from alert_evaluation import evaluate_alert, format_alert_message
from shared.config import VIETNAM_TZ
from shared.database import Database, close_db
from shared.neon.alerts import (
    expire_stale_alerts,
    get_active_alerts,
    get_recent_trigger_times,
    trigger_alert,
)
from shared.rules.settlement import get_settled_shares_by_ticker, is_sellable
from shared.telegram import send_telegram

SELL_ACTIONS: frozenset[str] = frozenset({"EXIT", "TRIM", "STOP"})

# Config
POLL_INTERVAL = 300  # 5 minutes
RSI_POLL_INTERVAL = 900  # 15 minutes for RSI checks
MAX_ANALYSES_PER_CYCLE = 3
DEDUP_WINDOW_MINUTES = 30
VNSTOCK_API_URL = os.environ.get("VNSTOCK_API_URL", "http://localhost:8000")
VNSTOCK_API_KEY = os.environ.get("VNSTOCK_API_KEY", "")

# Market sessions (VN time)
MARKET_SESSIONS = [
    (9, 0, 11, 30),  # Morning (includes ATO at 09:00)
    (13, 0, 14, 45),  # Afternoon (includes ATC at 14:30-14:45)
]


def is_market_hours() -> bool:
    """Check if current time is within VN market hours."""
    from shared.market_calendar import is_trading_day

    now = datetime.now(VIETNAM_TZ)
    if now.weekday() >= 5:
        return False
    if not is_trading_day(now.date()):
        return False
    for start_h, start_m, end_h, end_m in MARKET_SESSIONS:
        start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if start <= now <= end:
            return True
    return False


def _api_headers() -> dict:
    headers = {}
    if VNSTOCK_API_KEY:
        headers["X-API-Key"] = VNSTOCK_API_KEY
    return headers


async def fetch_current_prices(tickers: list[str]) -> dict[str, dict]:
    """Fetch current prices from vnstock-api batch endpoint."""
    if not tickers:
        return {}
    today = datetime.now(VIETNAM_TZ).strftime("%Y-%m-%d")
    symbols = ",".join(tickers)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{VNSTOCK_API_URL}/quote/history/batch",
            params={"symbols": symbols, "start": today, "end": today},
            headers=_api_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    prices = {}
    for symbol, payload in data.items():
        records = payload.get("data", [])
        if records:
            latest = records[-1]
            # API returns prices in thousands VND; condition values stored in full VND
            prices[symbol] = {
                "open": latest["open"] * 1000 if latest.get("open") else None,
                "high": latest["high"] * 1000 if latest.get("high") else None,
                "low": latest["low"] * 1000 if latest.get("low") else None,
                "close": latest["close"] * 1000 if latest.get("close") else None,
                "volume": latest.get("volume"),
            }
    return prices


async def fetch_technicals(tickers: list[str]) -> dict[str, dict]:
    """Fetch RSI and other technicals from vnstock-api."""
    if not tickers:
        return {}
    symbols = ",".join(tickers)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{VNSTOCK_API_URL}/technicals/batch",
            params={"symbols": symbols},
            headers=_api_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    technicals = {}
    for symbol, tech in data.items():
        if tech:
            technicals[symbol] = tech
    return technicals


def _needs_technicals(alert: dict) -> bool:
    """Check if any condition in the alert requires technical data (RSI/volume)."""
    tech_types = {"rsi_below", "rsi_above", "volume_spike"}
    return any(c.get("condition_type") in tech_types for c in alert.get("conditions", []))


async def trigger_gh_analysis(alert: dict, triggered_values: dict) -> bool:
    """Trigger GitHub Actions workflow for LLM analysis of a triggered alert."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO", "")
    if not token or not repo:
        missing = " and ".join(
            name for name, value in (("GITHUB_TOKEN", token), ("GITHUB_REPO", repo)) if not value
        )
        print(f"  {missing} not set, skipping analysis dispatch")
        return False

    conditions = [
        {"type": c.get("condition_type", ""), "value": str(c.get("condition_value", ""))}
        for c in alert.get("conditions", [])
    ]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.github.com/repos/{repo}/dispatches",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "event_type": "alert_triggered",
                    "client_payload": {
                        "alert_id": alert["id"],
                        "ticker": alert["ticker"],
                        "conditions": conditions,
                        "triggered_values": triggered_values,
                        "recommended_action": alert.get("recommended_action", "WATCH"),
                    },
                },
            )
        if resp.status_code == 204:
            print(f"  GH analysis dispatched for {alert['ticker']}")
            return True
        print(f"  GH dispatch failed: {resp.status_code} {resp.text[:100]}")
        return False
    except Exception as e:
        print(f"  GH dispatch error: {e}")
        return False


async def poll_cycle(fetch_rsi: bool = False):
    """Single poll cycle: check alerts, evaluate compound conditions, notify."""
    expired = await expire_stale_alerts()
    if expired:
        print(f"  Expired {expired} stale alerts")

    alerts = await get_active_alerts()
    if not alerts:
        return

    tickers = list({a["ticker"] for a in alerts})
    print(f"  Checking {len(alerts)} alerts across {len(tickers)} tickers")

    # T+2 settlement fetch and price fetch are independent round-trips.
    today_vn = datetime.now(VIETNAM_TZ).date()
    settled, prices = await asyncio.gather(
        get_settled_shares_by_ticker(today_vn),
        fetch_current_prices(tickers),
    )

    technicals = {}
    if fetch_rsi:
        # Only fetch technicals for tickers that have RSI/volume conditions
        tech_tickers = list({a["ticker"] for a in alerts if _needs_technicals(a)})
        if tech_tickers:
            technicals = await fetch_technicals(tech_tickers)

    # Dedup check
    alert_ids = [a["id"] for a in alerts]
    recent_triggers = await get_recent_trigger_times(alert_ids)
    now = datetime.now(UTC)
    dedup_cutoff = now - timedelta(minutes=DEDUP_WINDOW_MINUTES)

    analyses_run = 0

    for alert in alerts:
        # Skip if recently triggered (dedup window)
        last_trigger = recent_triggers.get(alert["id"])
        if last_trigger and last_trigger > dedup_cutoff:
            continue

        # T+2 settlement guard for sell-side alerts.
        action = (alert.get("recommended_action") or "").upper()
        if action in SELL_ACTIONS and not is_sellable(alert["ticker"], settled):
            print(f"  Skipped {alert['ticker']} {action}: unsettled (entry_date + 2td > today)")
            continue

        triggered, values = evaluate_alert(alert, prices, technicals)
        if not triggered:
            continue

        cond_summary = " & ".join(
            f"{c.get('condition_type')} @ {values.get(c.get('condition_type', ''), '?')}"
            for c in alert.get("conditions", [])
            if c.get("condition_type") in values
        )
        print(f"  TRIGGERED: {alert['ticker']} {cond_summary}")

        await trigger_alert(alert["id"], values)

        msg = format_alert_message(alert, values)
        try:
            await asyncio.to_thread(send_telegram, msg)
        except Exception as e:
            print(f"  Telegram send failed: {e}")

        if (
            alert.get("action_type") == "notify_and_analyze"
            and analyses_run < MAX_ANALYSES_PER_CYCLE
            and await trigger_gh_analysis(alert, values)
        ):
            analyses_run += 1


async def daemon_loop():
    """Main daemon loop — polls during market hours."""
    print("Alert Monitor started")
    print(f"  API: {VNSTOCK_API_URL}")
    print(f"  Poll interval: {POLL_INTERVAL}s")
    print(f"  RSI interval: {RSI_POLL_INTERVAL}s")

    rsi_counter = 0

    while True:
        if is_market_hours():
            try:
                fetch_rsi = rsi_counter == 0
                print(f"\n[{datetime.now(VIETNAM_TZ):%H:%M}] Polling (RSI: {fetch_rsi})...")
                await poll_cycle(fetch_rsi=fetch_rsi)
                rsi_counter = (rsi_counter + 1) % (RSI_POLL_INTERVAL // POLL_INTERVAL)
            except Exception as e:
                print(f"  Poll error: {e}")
        else:
            now = datetime.now(VIETNAM_TZ)
            if now.hour == 15 and now.minute < 10:
                try:
                    expired = await expire_stale_alerts()
                    if expired:
                        print(f"  EOD: Expired {expired} alerts")
                except Exception as e:
                    print(f"  EOD expire error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


async def main(once: bool = False):
    """Entry point with database lifecycle."""
    try:
        async with Database():
            if once:
                print("Running single poll cycle...")
                await poll_cycle(fetch_rsi=True)
            else:
                await daemon_loop()
    finally:
        await close_db()


if __name__ == "__main__":
    once = "--once" in sys.argv
    asyncio.run(main(once=once))
