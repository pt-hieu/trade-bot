#!/usr/bin/env python3
"""
Backfill USD/VND rates for macro_metrics rows stuck at 25860.

Fetches historical SBV reference rates and yfinance market rates from
the Lightsail API, then updates affected rows with correct values.

Requires SWINGY_ENV=production to run against prod DB.

Usage:
    SWINGY_ENV=production uv run python scripts/backfill_macro_rates.py
    SWINGY_ENV=production uv run python scripts/backfill_macro_rates.py --dry-run
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared.env import load_env

load_env()

import os

if not os.environ.get("VNSTOCK_API_URL"):
    raise RuntimeError("VNSTOCK_API_URL is not set — point it at your market-data service")


async def fetch_sbv_rates(start: str, end: str) -> dict[date, float]:
    """Fetch SBV reference rates for a date range. Returns {date: rate}."""
    from shared.vnstock_client import fetch_exchange_rate

    try:
        exr = await fetch_exchange_rate(start=start, end=end)
        data = exr.get("data", [])
    except Exception as e:
        print(f"  [SBV] fetch failed: {e}")
        return {}

    rates: dict[date, float] = {}
    for row in data:
        # Row has: report_time (index as string), last_updated, name, value, unit, source
        report_time = row.get("report_time")
        name = row.get("name") or ""
        value = row.get("value")

        # Only use "Tỷ giá trung tâm" (central rate), skip interbank (NaN → 0)
        if "trung t" not in name.lower():
            continue
        if not value or not isinstance(value, (int, float)) or not (20000 < value < 30000):
            continue

        try:
            scan_date = date.fromisoformat(str(report_time)[:10])
            rates[scan_date] = float(value)
        except Exception:
            continue

    return rates


async def fetch_yfinance_rates(start: str, end: str) -> dict[date, float]:
    """Fetch yfinance USDVND=X rates for a date range. Returns {date: rate}."""
    try:
        import yfinance as yf

        hist = yf.download("USDVND=X", start=start, end=end, progress=False)
        if hist is None or hist.empty:
            print("  [yfinance] No data returned")
            return {}
        # Flatten MultiIndex if present
        if hasattr(hist.columns, "levels"):
            hist.columns = hist.columns.get_level_values(0)
        rates: dict[date, float] = {}
        for dt, close_val in hist["Close"].items():  # type: ignore[union-attr]
            d = dt.date() if hasattr(dt, "date") else dt  # type: ignore[union-attr]
            rates[d] = float(close_val)  # type: ignore[arg-type]
        return rates
    except Exception as e:
        print(f"  [yfinance] fetch failed: {e}")
        return {}


async def _recalculate_regime_all_rows(db, dry_run: bool) -> int:
    """Phase 2: Recalculate global_risk_regime for ALL rows from stored signals.

    Fixes mismatches where backfill (or old source confusion) left stale regime values
    that don't match the stored signals.
    """
    from agents.macro import (
        calculate_global_regime,
        classify_dxy,
        classify_oil,
        classify_usd_vnd,
        classify_vix,
    )

    rows = await db.fetch_all(
        """
        SELECT scan_date, dxy_value, dxy_change_pct, vix_value,
               usd_vnd_rate, usd_vnd_source, usd_vnd_signal_value,
               oil_price, oil_change_pct, global_risk_regime
        FROM macro_metrics
        ORDER BY scan_date
        """
    )

    updated = 0
    mismatches = 0
    for row in rows:
        scan_date = (
            row["scan_date"].date() if hasattr(row["scan_date"], "date") else row["scan_date"]
        )
        dxy_value = float(row["dxy_value"] or 0)
        dxy_change = float(row["dxy_change_pct"] or 0)
        vix_value = float(row["vix_value"] or 0)
        usd_vnd_rate = float(row["usd_vnd_rate"] or 0)
        usd_vnd_source = row.get("usd_vnd_source") or "sbv"
        stored_usd_vnd_signal = row["usd_vnd_signal_value"] or "STABLE"
        oil_price = float(row["oil_price"] or 0)
        oil_change = float(row["oil_change_pct"] or 0)
        stored_regime = row["global_risk_regime"]

        # Reclassify ALL signals from raw values (including USD/VND)
        dxy_signal = classify_dxy(dxy_value, dxy_change) if dxy_value > 0 else "NEUTRAL"
        vix_signal = classify_vix(vix_value) if vix_value > 0 else "MODERATE"
        usd_vnd_signal = (
            classify_usd_vnd(usd_vnd_rate, usd_vnd_source) if usd_vnd_rate > 0 else "STABLE"
        )
        oil_signal = classify_oil(oil_price, oil_change) if oil_price > 0 else "NORMAL"
        expected_regime = calculate_global_regime(
            dxy_signal, vix_signal, usd_vnd_signal, False, oil_signal
        )

        regime_changed = expected_regime != stored_regime
        signal_changed = usd_vnd_signal != stored_usd_vnd_signal
        if regime_changed or signal_changed:
            mismatches += 1
            print(
                f"  {scan_date}: regime {stored_regime} → {expected_regime}, "
                f"USD/VND signal {stored_usd_vnd_signal} → {usd_vnd_signal} "
                f"(DXY={dxy_signal}, VIX={vix_signal}, Oil={oil_signal})"
            )
            if not dry_run:
                await db.execute(
                    "UPDATE macro_metrics SET global_risk_regime = $2, "
                    "usd_vnd_signal_value = $3 WHERE scan_date = $1",
                    scan_date,
                    expected_regime,
                    usd_vnd_signal,
                )
                updated += 1

    print(f"\n  Regime mismatches found: {mismatches}")
    return updated


async def _main(dry_run: bool) -> None:
    from agents.macro import classify_usd_vnd
    from shared.database import Database, close_db

    print("=== Backfill USD/VND rates + regime recalculation ===")
    print(f"Mode: {'DRY RUN' if dry_run else 'PRODUCTION'}")

    # Affected dates range
    start = "2026-01-28"  # extend back to catch pre-migration-090 source issues
    end = "2026-02-28"

    print(f"\nFetching SBV rates {start} → {end}...")
    sbv_rates = await fetch_sbv_rates(start, end)
    print(f"  Got {len(sbv_rates)} SBV rate(s): {sbv_rates}")

    print(f"\nFetching yfinance rates {start} → {end}...")
    yf_rates = await fetch_yfinance_rates(start, end)
    print(f"  Got {len(yf_rates)} yfinance rate(s)")

    # Dates where USD/VND needs correction (had stale 25860 or missing source)
    affected_dates = [
        date(2026, 2, 10),
        date(2026, 2, 11),
        date(2026, 2, 12),
        date(2026, 2, 13),
        date(2026, 2, 17),
        date(2026, 2, 23),
        date(2026, 2, 24),
        date(2026, 2, 25),
        date(2026, 2, 26),
        date(2026, 2, 27),
    ]

    print(f"\nPhase 1: Updating USD/VND rates for {len(affected_dates)} dates...")

    async with Database() as db:
        updated = 0
        for scan_date in affected_dates:
            sbv_rate = sbv_rates.get(scan_date)
            yf_rate = yf_rates.get(scan_date)

            # Determine primary rate and source
            if sbv_rate:
                usd_vnd_rate = sbv_rate
                usd_vnd_source = "sbv"
                usd_vnd_spread = round(yf_rate - sbv_rate, 2) if yf_rate else None
            elif yf_rate:
                usd_vnd_rate = yf_rate
                usd_vnd_source = "yfinance"
                usd_vnd_spread = None
            else:
                print(f"  {scan_date}: no data from either source, skipping")
                continue

            usd_vnd_signal = classify_usd_vnd(usd_vnd_rate, usd_vnd_source or "sbv")

            print(
                f"  {scan_date}: rate={usd_vnd_rate:.0f} source={usd_vnd_source} "
                f"spread={usd_vnd_spread} signal={usd_vnd_signal}"
            )

            if not dry_run:
                await db.execute(
                    """
                    UPDATE macro_metrics
                    SET usd_vnd_rate = $2,
                        usd_vnd_signal_value = $3,
                        usd_vnd_source = $4,
                        usd_vnd_spread = $5
                    WHERE scan_date = $1
                    """,
                    scan_date,
                    usd_vnd_rate,
                    usd_vnd_signal,
                    usd_vnd_source,
                    usd_vnd_spread,
                )
                updated += 1

        print("\nPhase 2: Recalculating regime for all rows from stored signals...")
        regime_updated = await _recalculate_regime_all_rows(db, dry_run)

        await close_db()

    if dry_run:
        print("\nDry run complete — no DB writes.")
    else:
        print(f"\nPhase 1: Updated {updated} USD/VND rows.")
        print(f"Phase 2: Updated {regime_updated} regime rows.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill USD/VND rates in macro_metrics")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    if not args.dry_run and os.environ.get("SWINGY_ENV") != "production":
        print("ERROR: Set SWINGY_ENV=production to run against production DB.")
        sys.exit(1)

    asyncio.run(_main(args.dry_run))


if __name__ == "__main__":
    main()
