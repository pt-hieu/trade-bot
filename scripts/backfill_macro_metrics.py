#!/usr/bin/env python3
"""
One-off backfill: populate macro_metrics for dates missing data.

Uses the Lightsail API (yfinance-backed) to fetch historical DXY, VIX, and other
indicators per date, then computes signals and regime deterministically.

Usage:
    SWINGY_ENV=production uv run python scripts/backfill_macro_metrics.py [--dry-run]
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared.database import Database, get_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

LIGHTSAIL_SSH_TARGET = os.environ.get("LIGHTSAIL_SSH_TARGET", "ubuntu@lightsail.example.com")
LIGHTSAIL_SSH_KEY = os.environ.get("LIGHTSAIL_SSH_KEY", str(Path.home() / ".ssh/vnstock-api"))


async def fetch_yfinance_for_date(scan_date: date) -> dict | None:
    """Fetch macro indicators from yfinance for a specific historical date.

    Runs on Lightsail via SSH since yfinance is installed there.
    Returns dict matching _fetch_macro_data() shape, or None on failure.
    """
    import subprocess

    date_str = scan_date.isoformat()
    next_day = (scan_date + timedelta(days=1)).isoformat()

    # Run yfinance on Lightsail to get historical data for this specific date
    script = f"""
import json, yfinance as yf, gc
result = {{}}
tickers = [
    ("DX-Y.NYB", "dxy"), ("^VIX", "vix"), ("USDVND=X", "usd_vnd"),
    ("HG=F", "copper"), ("CL=F", "oil"), ("^TNX", "us_10y"),
    ("000001.SS", "shanghai"), ("^GSPC", "sp500"), ("^IXIC", "nasdaq"), ("^DJI", "dow"),
]
for ticker, key in tickers:
    try:
        hist = yf.Ticker(ticker).history(start="{date_str}", end="{next_day}")
        if len(hist) >= 1:
            current = float(hist["Close"].iloc[-1])
            # Try to get prev day for change_pct
            hist_prev = yf.Ticker(ticker).history(start="{(scan_date - timedelta(days=5)).isoformat()}", end="{next_day}")
            if len(hist_prev) >= 2:
                previous = float(hist_prev["Close"].iloc[-2])
                change_pct = round((current - previous) / previous * 100, 2)
            else:
                change_pct = 0.0
            result[key] = {{"value": round(current, 4), "change_pct": change_pct}}
        else:
            result[key] = {{"value": 0.0, "change_pct": 0.0}}
    except Exception as e:
        result[key] = {{"value": 0.0, "change_pct": 0.0}}
    finally:
        gc.collect()
print(json.dumps(result))
"""
    try:
        proc = subprocess.run(
            [
                "ssh",
                "-i",
                LIGHTSAIL_SSH_KEY,
                LIGHTSAIL_SSH_TARGET,
                f"/opt/vnstock-api/.venv/bin/python -c '{script}'",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            logger.warning("yfinance fetch failed for %s: %s", date_str, proc.stderr[:200])
            return None

        import json

        # Parse last line (skip vnstock upgrade warnings)
        lines = proc.stdout.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{"):
                raw = json.loads(line)
                break
        else:
            logger.warning("No JSON output for %s", date_str)
            return None

        dxy = raw.get("dxy", {})
        vix = raw.get("vix", {})
        usd_vnd = raw.get("usd_vnd", {})
        copper = raw.get("copper", {})
        oil = raw.get("oil", {})
        us_10y = raw.get("us_10y", {})
        shanghai = raw.get("shanghai", {})
        sp500 = raw.get("sp500", {})
        nasdaq = raw.get("nasdaq", {})
        dow = raw.get("dow", {})

        return {
            "dxy_value": dxy.get("value", 0.0),
            "dxy_change_pct": dxy.get("change_pct", 0.0),
            "vix_value": vix.get("value", 0.0),
            "vix_change_pct": vix.get("change_pct", 0.0),
            "usd_vnd_rate": usd_vnd.get("value", 0.0),
            "usd_vnd_source": "yfinance",
            "usd_vnd_spread": None,
            "copper_price": copper.get("value"),
            "copper_change_pct": copper.get("change_pct"),
            "oil_price": oil.get("value"),
            "oil_change_pct": oil.get("change_pct"),
            "us_10y_yield": us_10y.get("value"),
            "us_10y_change_pct": us_10y.get("change_pct"),
            "shanghai_close": shanghai.get("value"),
            "shanghai_change_pct": shanghai.get("change_pct"),
            "sp500_close": sp500.get("value"),
            "sp500_change_pct": sp500.get("change_pct"),
            "nasdaq_close": nasdaq.get("value"),
            "nasdaq_change_pct": nasdaq.get("change_pct"),
            "dow_close": dow.get("value"),
            "dow_change_pct": dow.get("change_pct"),
        }
    except subprocess.TimeoutExpired:
        logger.warning("Timeout fetching yfinance for %s", date_str)
        return None
    except Exception as error:
        logger.warning("Error fetching yfinance for %s: %s", date_str, error)
        return None


async def backfill():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    from agents.macro import (
        MISSING_SIGNAL,
        MISSING_SIGNAL_DEFAULTS,
        _is_valid_number,
        calculate_global_regime,
        classify_dxy,
        classify_oil,
        classify_usd_vnd,
        classify_vix,
    )
    from shared.neon import insert_macro_metrics

    async with Database():
        db = await get_db()

        # Find dates with daily_records but no macro_metrics
        since = date.today() - timedelta(days=args.days)
        missing = await db.fetch_all(
            """
            SELECT DISTINCT dr.record_date
            FROM daily_records dr
            LEFT JOIN macro_metrics mm ON mm.scan_date = dr.record_date
            WHERE dr.record_date >= $1 AND mm.id IS NULL
            ORDER BY dr.record_date ASC
            """,
            since,
        )
        logger.info("Found %d dates missing macro_metrics", len(missing))

        if args.dry_run:
            for row in missing:
                logger.info("  Would backfill: %s", row["record_date"])
            return

        inserted = 0
        for row in missing:
            scan_date = row["record_date"]
            if isinstance(scan_date, str):
                scan_date = date.fromisoformat(scan_date)

            logger.info("Fetching %s...", scan_date)
            data = await fetch_yfinance_for_date(scan_date)
            if not data:
                logger.warning("  No data for %s, skipping", scan_date)
                continue

            # Zero-data guard (matches fetch_macro_metrics behavior)
            dxy_valid = _is_valid_number(data["dxy_value"]) and data["dxy_value"] != 0
            vix_valid = _is_valid_number(data["vix_value"]) and data["vix_value"] != 0
            if not dxy_valid and not vix_valid:
                logger.warning("  %s: DXY and VIX both missing/zero, skipping", scan_date)
                continue

            # Compute signals deterministically (NaN-safe via MISSING sentinel)
            dxy_signal = classify_dxy(data["dxy_value"], data["dxy_change_pct"])
            vix_signal = classify_vix(data["vix_value"])
            usd_vnd_signal = classify_usd_vnd(
                data["usd_vnd_rate"], data.get("usd_vnd_source") or "yfinance"
            )

            # If any critical signal is MISSING, default to CAUTIOUS
            signals = [dxy_signal, vix_signal, usd_vnd_signal]
            if MISSING_SIGNAL in signals:
                logger.warning("  %s: MISSING signals detected, defaulting to CAUTIOUS", scan_date)
                dxy_signal = (
                    dxy_signal if dxy_signal != MISSING_SIGNAL else MISSING_SIGNAL_DEFAULTS["dxy"]
                )
                vix_signal = (
                    vix_signal if vix_signal != MISSING_SIGNAL else MISSING_SIGNAL_DEFAULTS["vix"]
                )
                usd_vnd_signal = (
                    usd_vnd_signal
                    if usd_vnd_signal != MISSING_SIGNAL
                    else MISSING_SIGNAL_DEFAULTS["usd_vnd"]
                )

            oil_price = data.get("oil_price")
            oil_change = data.get("oil_change_pct") or 0.0
            if not _is_valid_number(oil_price) or oil_price is None or oil_price <= 0:
                oil_signal = "NORMAL"
            else:
                oil_signal = classify_oil(oil_price, oil_change)
                if oil_signal == MISSING_SIGNAL:
                    oil_signal = "NORMAL"

            # Note: active_geopolitical_phase intentionally omitted for historical backfills.
            # Geopolitical context is time-sensitive and cannot be reconstructed from DB alone.
            # has_event_within_3_days=False: historical events not reconstructable.
            regime = calculate_global_regime(
                dxy_signal,
                vix_signal,
                usd_vnd_signal,
                has_event_within_3_days=False,
                oil_signal=oil_signal,
            )

            # Build the full dict for insert_macro_metrics
            metrics = {
                **data,
                "dxy_signal": dxy_signal,
                "vix_signal": vix_signal,
                "usd_vnd_signal": usd_vnd_signal,
                "oil_signal": oil_signal,
                "global_risk_regime": regime,
                "interpretation": f"Backfilled: {regime}. DXY={data['dxy_value']}, VIX={data['vix_value']}.",
            }

            ok = await insert_macro_metrics(scan_date, metrics)
            if ok:
                inserted += 1
                logger.info(
                    "  %s: %s (DXY=%.1f, VIX=%.1f)",
                    scan_date,
                    regime,
                    data["dxy_value"],
                    data["vix_value"],
                )
            else:
                logger.warning("  %s: insert failed", scan_date)

        logger.info("Backfill complete: %d/%d macro_metrics inserted", inserted, len(missing))


if __name__ == "__main__":
    asyncio.run(backfill())
