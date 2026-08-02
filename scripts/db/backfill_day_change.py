#!/usr/bin/env python3
"""
One-time backfill: compute day_change for historical daily_evaluations.

day_change was not persisted before ~2026-03-17. This script fetches historical
OHLC from vnstock API and computes day_change = (close - prev_close) / prev_close * 100.

Usage:
    uv run python scripts/db/backfill_day_change.py --dry-run
    SWINGY_ENV=production uv run python scripts/db/backfill_day_change.py
"""

import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database import Database, get_db
from shared.vnstock_client import fetch_history


async def get_rows_needing_day_change() -> list[dict]:
    """Get evaluations with NULL day_change that are scoreable."""
    db = await get_db()
    rows = await db.fetch_all("""
        SELECT de.id, de.ticker, dr.record_date
        FROM daily_evaluations de
        JOIN daily_records dr ON dr.id = de.record_id
        WHERE de.day_change IS NULL
          AND de.status NOT IN ('EXCLUDED', 'MISSED')
        ORDER BY dr.record_date, de.ticker
    """)
    return [dict(r) for r in rows]


def group_by_ticker(rows: list[dict]) -> dict[str, list[dict]]:
    """Group rows by ticker for batched API calls."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        ticker = row["ticker"]
        if ticker not in grouped:
            grouped[ticker] = []
        grouped[ticker].append(row)
    return grouped


async def fetch_price_bars(ticker: str, start_date, end_date) -> dict:
    """Fetch OHLC bars for ticker covering date range + 5 extra days for prev_close."""
    padded_start = (start_date - timedelta(days=10)).strftime("%Y-%m-%d")
    padded_end = end_date.strftime("%Y-%m-%d")
    result = await fetch_history(ticker, start=padded_start, end=padded_end)
    bars = result.get("data") or []
    # Index by date string for fast lookup
    bar_map = {}
    sorted_bars = sorted(bars, key=lambda bar: bar.get("time") or "")
    for index, bar in enumerate(sorted_bars):
        bar_date = (bar.get("time") or "")[:10]
        bar["_prev_close"] = sorted_bars[index - 1].get("close") if index > 0 else None
        bar_map[bar_date] = bar
    return bar_map


def compute_day_change(bar: dict) -> float | None:
    """Compute day_change from bar data, matching compute.py logic."""
    close = bar.get("close") or 0
    prev_close = bar.get("_prev_close") or 0
    opening = bar.get("open") or 0

    if close <= 0:
        return None
    if prev_close > 0:
        return round((close - prev_close) / prev_close * 100, 2)
    if opening > 0:
        return round((close - opening) / opening * 100, 2)
    return None


async def run_backfill(dry_run: bool = True):
    """Main backfill routine."""
    async with Database():
        rows = await get_rows_needing_day_change()
        print(f"Found {len(rows)} evaluations with NULL day_change")

        if not rows:
            print("Nothing to backfill.")
            return

        grouped = group_by_ticker(rows)
        print(f"Across {len(grouped)} unique tickers")

        db = await get_db()
        total_updated = 0
        total_skipped = 0
        total_failed = 0

        for ticker_index, (ticker, ticker_rows) in enumerate(sorted(grouped.items())):
            dates = [r["record_date"] for r in ticker_rows]
            min_date = min(dates)
            max_date = max(dates)
            print(
                f"\n[{ticker_index + 1}/{len(grouped)}] {ticker} — {len(ticker_rows)} rows ({min_date} to {max_date})"
            )

            try:
                bar_map = await fetch_price_bars(ticker, min_date, max_date)
                if not bar_map:
                    print(f"  WARNING: No price data from API for {ticker}")
                    total_failed += len(ticker_rows)
                    continue

                for row in ticker_rows:
                    date_str = row["record_date"].strftime("%Y-%m-%d")
                    bar = bar_map.get(date_str)
                    if not bar:
                        print(f"  SKIP {date_str}: no bar data")
                        total_skipped += 1
                        continue

                    day_change = compute_day_change(bar)
                    if day_change is None:
                        print(f"  SKIP {date_str}: cannot compute day_change (close=0)")
                        total_skipped += 1
                        continue

                    if dry_run:
                        print(f"  [DRY] {date_str}: day_change={day_change:+.2f}%")
                        total_updated += 1
                    else:
                        await db.execute(
                            "UPDATE daily_evaluations SET day_change = $1 WHERE id = $2",
                            day_change,
                            row["id"],
                        )
                        total_updated += 1

            except Exception as exception:
                print(f"  ERROR for {ticker}: {exception}")
                total_failed += len(ticker_rows)

            # Rate limit between tickers
            if not dry_run and ticker_index < len(grouped) - 1:
                await asyncio.sleep(0.5)

        prefix = "would be " if dry_run else ""
        print(
            f"\nBackfill complete. {prefix}Updated: {total_updated}, skipped: {total_skipped}, failed: {total_failed}"
        )


def main():
    parser = argparse.ArgumentParser(description="Backfill day_change for historical evaluations")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    asyncio.run(run_backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
