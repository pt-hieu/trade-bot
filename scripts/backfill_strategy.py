#!/usr/bin/env python3
"""
Backfill strategy classification on historical daily_recommendations.

For each BUY/LIMIT_BUY/ADD rec with NULL strategy, fetches historical
technicals via fetch_technicals_async (with end_date = scan_date), runs
classify_strategy(), and UPDATEs the row.

Usage:
    SWINGY_ENV=production uv run python scripts/backfill_strategy.py
"""

import asyncio
import logging
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared.database import Database, close_db

logger = logging.getLogger(__name__)


async def _main() -> None:
    from agents.tools.strategy_classifier import classify_strategy
    from data.technicals import fetch_technicals_async
    from shared.database import get_db
    from shared.trading_config import init_trading_config

    await init_trading_config()

    db = await get_db()

    rows = await db.fetch_all(
        """
        SELECT drec.id, drec.ticker, dr.record_date
        FROM daily_recommendations drec
        JOIN daily_records dr ON drec.record_id = dr.id
        WHERE drec.action IN ('BUY', 'LIMIT_BUY', 'ADD')
          AND drec.strategy IS NULL
        ORDER BY dr.record_date
        """
    )

    if not rows:
        print("No recs need strategy backfill.")
        return

    print(f"Backfilling strategy for {len(rows)} recs...\n")

    # Group recs by scan_date to batch API calls
    recs_by_date: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        record_date = row["record_date"]
        date_str = (
            record_date.strftime("%Y-%m-%d") if isinstance(record_date, date) else str(record_date)
        )
        recs_by_date[date_str].append(dict(row))

    updated = 0
    failed = 0

    for scan_date_str, date_recs in sorted(recs_by_date.items()):
        tickers = list({rec["ticker"] for rec in date_recs})
        print(f"\n[{scan_date_str}] Fetching technicals for {tickers}...")

        try:
            watchlist = {"backfill": tickers}
            tech_map = await fetch_technicals_async(watchlist, end_date=scan_date_str)
        except Exception as exception:
            logger.warning("Technicals fetch failed for %s: %s", scan_date_str, exception)
            print(f"  SKIP all {len(date_recs)} recs: {exception}")
            failed += len(date_recs)
            continue

        for rec in date_recs:
            rec_id = rec["id"]
            ticker = rec["ticker"]
            tech_data = tech_map.get(ticker)

            if not tech_data or not tech_data.get("close"):
                print(f"  SKIP {ticker}: no technicals data")
                failed += 1
                continue

            strategy_classification = classify_strategy(tech_data)

            await db.execute(
                """
                UPDATE daily_recommendations
                SET strategy = $1, strategy_confidence = $2
                WHERE id = $3
                """,
                strategy_classification.strategy,
                round(strategy_classification.confidence, 2),
                rec_id,
            )
            print(
                f"  {ticker}: {strategy_classification.strategy} "
                f"(confidence={strategy_classification.confidence:.2f})"
            )
            updated += 1

    print(f"\nDone: {updated} updated, {failed} skipped")


async def _run() -> None:
    try:
        async with Database():
            await _main()
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(_run())
