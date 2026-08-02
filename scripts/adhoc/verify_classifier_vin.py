#!/usr/bin/env python3
"""Pre-code verification V1 — does strategy_classifier emit TREND/MOMENTUM/BREAKOUT
for Vin-family on historical rally dates? Phase 0 gate for ExitStrategy refactor.

Usage:
    uv run python scripts/adhoc/verify_classifier_vin.py \\
      --dates 2025-12-10 2025-12-15 2025-12-20 \\
      --tickers VHM VIC VRE VPB TCB
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.tools.strategy_classifier import classify_strategy
from shared.database import Database
from shared.neon.catalyst_summaries import compute_catalyst_boost_set

ATR_TRAIL_STRATEGIES = {"TREND", "MOMENTUM", "BREAKOUT"}


async def _fetch_technicals_snapshot(db: Database, ticker: str, scan_date: str) -> dict | None:
    """Pull the daily_technicals row for ticker on scan_date."""
    rows = await db.fetch_all(
        """
        SELECT ticker, close_vnd AS close, rsi, ma20, ma50, volume_vs_avg,
               trend, pattern, levels, atr, macd_histogram
        FROM daily_technicals
        WHERE ticker = $1 AND scan_date = $2::date
        LIMIT 1
        """,
        ticker.upper(),
        scan_date,
    )
    if not rows:
        return None
    row = dict(rows[0])
    # Normalize JSONB dict fields
    for key in ("trend", "pattern", "levels"):
        value = row.get(key)
        if value is None:
            row[key] = {}
    return row


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", required=True, help="ISO dates e.g. 2025-12-15")
    parser.add_argument("--tickers", nargs="+", required=True, help="VHM VIC VRE ...")
    args = parser.parse_args()

    summary = {"total": 0, "missing": 0, "tf_tagged": 0, "classified": {}}
    rows_out: list[str] = []

    # Fetch catalyst-boosted ticker set once — threaded into classify_strategy
    # so MEAN_REVERSION → MOMENTUM promotion fires for catalyst-active names.
    try:
        boosted = await compute_catalyst_boost_set()
    except Exception as error:  # noqa: BLE001
        print(f"WARN: catalyst boost fetch failed ({error}); proceeding without promotion")
        boosted = {}
    boosted_upper = {t.upper() for t in boosted}
    print(f"Catalyst-boosted tickers: {sorted(boosted_upper) or '<none>'}")

    async with Database() as db:
        for scan_date in args.dates:
            for ticker in args.tickers:
                summary["total"] += 1
                snapshot = await _fetch_technicals_snapshot(db, ticker, scan_date)
                if snapshot is None:
                    summary["missing"] += 1
                    rows_out.append(f"{scan_date} {ticker:6s} MISSING (no daily_technicals row)")
                    continue
                has_catalyst = ticker.upper() in boosted_upper
                try:
                    classification = classify_strategy(
                        snapshot,
                        rsi_at_swing_low=None,
                        has_positive_active_catalyst=has_catalyst,
                    )
                except Exception as error:  # noqa: BLE001
                    rows_out.append(f"{scan_date} {ticker:6s} ERROR {error}")
                    continue
                strategy = classification.strategy
                summary["classified"][strategy] = summary["classified"].get(strategy, 0) + 1
                if strategy in ATR_TRAIL_STRATEGIES:
                    summary["tf_tagged"] += 1
                catalyst_tag = " +catalyst" if has_catalyst else ""
                rows_out.append(
                    f"{scan_date} {ticker:6s} {strategy:14s} "
                    f"conf={classification.confidence:.2f} "
                    f"signals={classification.matched_signals}{catalyst_tag}"
                )

    print("=" * 80)
    print("VIN-FAMILY CLASSIFIER VERIFICATION (Phase 0 V1)")
    print("=" * 80)
    for row in rows_out:
        print(row)
    print("-" * 80)
    print(f"Total (ticker, date) pairs: {summary['total']}")
    print(f"Missing daily_technicals:   {summary['missing']}")
    print(f"Classifications: {summary['classified']}")
    print(f"ATR_TRAIL-eligible tags (TREND/MOMENTUM/BREAKOUT): {summary['tf_tagged']}")
    print("=" * 80)
    if summary["tf_tagged"] == 0 and summary["total"] > summary["missing"]:
        print(
            "WARNING: zero TF tags on rally dates — classifier likely needs catalyst "
            "promotion before ExitStrategy refactor can deliver value."
        )
        return 2  # non-zero but distinct from hard error
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
