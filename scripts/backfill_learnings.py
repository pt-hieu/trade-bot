#!/usr/bin/env python3
"""
Recompute learnings aggregates from DB historical daily_records.

Loads last N days of records from DB, runs them through update_learnings()
to recompute summary stats and patterns, then persists aggregates back to DB.

Requires SWINGY_ENV=production to run against prod DB.

Usage:
    SWINGY_ENV=production uv run python scripts/backfill_learnings.py
    SWINGY_ENV=production uv run python scripts/backfill_learnings.py --days 14
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared.database import Database, close_db


async def _main(days: int) -> None:
    from agents.retro.patterns import extract_patterns
    from retro_helpers.learnings import (
        _merge_patterns,
        load_learnings_from_db,
    )
    from shared.neon import get_swing_watchlist
    from shared.neon.insert_learnings import insert_learnings
    from shared.neon.insert_strategy_insights import insert_strategy_insights

    print(f"\nRecomputing learnings from last {days} days of DB records...")

    print("\n[1/4] Loading records from DB...")
    learnings = await load_learnings_from_db(days)
    records = learnings.get("daily_records", [])
    if not records:
        print("No records found. Nothing to recompute.")
        return
    print(f"  Found {len(records)} day(s).")

    print("\n[2/4] Building sector map from watchlist...")
    watchlist = await get_swing_watchlist()
    sector_map: dict[str, str] = {}
    if watchlist:
        for sector_name, tickers in watchlist.items():
            for ticker in tickers:
                sector_map[ticker] = sector_name
    print(f"  {len(sector_map)} tickers mapped to sectors.")

    print("\n[3/4] Extracting patterns (deterministic)...")
    patterns = await extract_patterns(records, days, sector_map)
    print(
        f"  Winning: {len(patterns['winning_patterns'])}, "
        f"Losing: {len(patterns['losing_patterns'])}, "
        f"Sector: {len(patterns['sector_insights'])}"
    )

    # Merge extracted patterns into learnings
    if patterns.get("winning_patterns"):
        learnings["winning_patterns"] = _merge_patterns([], patterns["winning_patterns"])
    if patterns.get("losing_patterns"):
        learnings["losing_patterns"] = _merge_patterns([], patterns["losing_patterns"])
    if patterns.get("sector_insights"):
        learnings["sector_insights"] = patterns["sector_insights"]
    if patterns.get("ticker_insights"):
        learnings["ticker_insights"] = patterns["ticker_insights"]
    if patterns.get("calibration_insights"):
        learnings["calibration_insights"] = patterns["calibration_insights"]
    if patterns.get("strategy_insights"):
        learnings["strategy_patterns"] = {
            s["strategy"]: {"win_rate": s["win_rate"], "sample_size": s["sample_size"]}
            for s in patterns["strategy_insights"]
        }
    learnings["last_updated"] = records[-1]["date"]

    print("\n[4/4] Persisting learnings to DB...")
    learnings_ok, strategy_ok = await asyncio.gather(
        insert_learnings(learnings),
        insert_strategy_insights(learnings.get("strategy_patterns", {}), records[-1]["date"]),
    )
    if learnings_ok:
        print("  DB: learnings updated.")
    else:
        print("  WARNING: learnings update failed.")
    if strategy_ok:
        print("  DB: strategy insights updated.")

    print(f"\n{'=' * 50}")
    print("Recompute complete!")
    summary = learnings.get("summary", {})
    print(f"  Days:              {summary.get('total_days', 0)}")
    print(f"  Total evals:       {summary.get('total_recs', 0)}")
    print(f"  Win rate:          {summary.get('overall_win_rate', 0):.1f}%")
    print(f"  Winning patterns:  {len(learnings.get('winning_patterns', []))}")
    print(f"  Losing patterns:   {len(learnings.get('losing_patterns', []))}")
    print(f"  Sector insights:   {len(learnings.get('sector_insights', []))}")
    print(f"{'=' * 50}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute learnings from DB")
    parser.add_argument(
        "--days", type=int, default=30, help="Days of history to recompute (default: 30)"
    )
    args = parser.parse_args()
    asyncio.run(_run(args.days))


async def _run(days: int) -> None:
    try:
        async with Database():
            from shared.trading_config import init_trading_config

            await init_trading_config()
            await _main(days)
    finally:
        await close_db()


if __name__ == "__main__":
    main()
