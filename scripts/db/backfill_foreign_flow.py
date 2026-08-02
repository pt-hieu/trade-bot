#!/usr/bin/env python3
"""
One-time backfill: enrich existing foreign_flow_details rows with per-ticker data.

Fetches buy/sell breakdown, ownership %, and remaining room from the Lightsail API
for each historical date that has foreign flow data.

Usage:
    uv run python scripts/db/backfill_foreign_flow.py --dry-run
    DATABASE_URL="<owner_url>" uv run python scripts/db/backfill_foreign_flow.py
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database import Database, get_db


async def get_dates_with_details() -> list[dict]:
    """Get all scan_dates that have foreign_flow_details, grouped with tickers."""
    db = await get_db()
    rows = await db.fetch_all("""
        SELECT ff.scan_date, array_agg(DISTINCT fd.ticker) AS tickers
        FROM foreign_flows ff
        JOIN foreign_flow_details fd ON fd.flow_id = ff.id
        WHERE fd.ownership_pct IS NULL
        GROUP BY ff.scan_date
        ORDER BY ff.scan_date DESC
    """)
    return [{"scan_date": r["scan_date"], "tickers": r["tickers"]} for r in rows]


async def fetch_per_ticker(tickers: list[str], scan_date: date) -> dict:
    """Fetch per-ticker foreign flow for a specific date."""
    from shared.vnstock_client import fetch_foreign_flow

    date_str = scan_date.strftime("%Y-%m-%d")
    return await fetch_foreign_flow(tickers, start=date_str, end=date_str)


def _unwrap(raw: dict) -> dict | None:
    """Unwrap {data: [{...}], count} -> inner dict."""
    if not isinstance(raw, dict) or "error" in raw:
        return None
    rows = raw.get("data", [])
    if rows and isinstance(rows, list):
        return rows[0]
    if "fr_net_value" in raw:
        return raw
    return None


async def update_details(scan_date: date, per_stock: dict, dry_run: bool) -> int:
    """Update foreign_flow_details rows with enriched data."""
    db = await get_db()
    updated = 0

    for ticker, raw in per_stock.items():
        data = _unwrap(raw)
        if not data:
            continue

        buy_val = float(data.get("fr_buy_value", 0) or 0) / 1e9
        sell_val = float(data.get("fr_sell_value", 0) or 0) / 1e9
        net_val = float(data.get("fr_net_value", 0) or 0) / 1e9
        ownership = data.get("fr_ownership")
        room = data.get("fr_remaining_room")

        own_pct = float(ownership) if ownership is not None else None
        remaining = int(room) if room is not None else None

        if dry_run:
            print(f"    [DRY] {ticker}: net={net_val:+.3f}B own={own_pct} room={remaining}")
            updated += 1
            continue

        # Use separate query for remaining_room to avoid asyncpg int32 codec issue
        result = await db.execute(
            """
            UPDATE foreign_flow_details fd
            SET buy_value_billion = $1, sell_value_billion = $2,
                net_value_billion = $3, ownership_pct = $4
            FROM foreign_flows ff
            WHERE fd.flow_id = ff.id
              AND ff.scan_date = $5
              AND fd.ticker = $6
        """,
            round(buy_val, 3),
            round(sell_val, 3),
            round(net_val, 3),
            own_pct,
            scan_date,
            ticker,
        )

        if remaining is not None:
            # Embed integer directly — asyncpg int32 codec can't handle large values
            await db.execute(
                f"""
                UPDATE foreign_flow_details fd
                SET remaining_room = {int(remaining)}
                FROM foreign_flows ff
                WHERE fd.flow_id = ff.id
                  AND ff.scan_date = $1
                  AND fd.ticker = $2
            """,
                scan_date,
                ticker,
            )

        if result and "UPDATE" in str(result):
            updated += 1

    return updated


async def run_backfill(dry_run: bool = True):
    """Main backfill routine."""
    async with Database():
        dates = await get_dates_with_details()
        print(f"Found {len(dates)} dates with un-enriched foreign flow details")

        if not dates:
            print("Nothing to backfill.")
            return

        total_updated = 0
        for i, entry in enumerate(dates):
            scan_date = entry["scan_date"]
            tickers = [t for t in entry["tickers"] if t]
            print(
                f"\n[{i + 1}/{len(dates)}] {scan_date} — {len(tickers)} tickers: {', '.join(tickers[:5])}"
            )

            try:
                per_stock = await fetch_per_ticker(tickers, scan_date)
                count = await update_details(scan_date, per_stock, dry_run)
                total_updated += count
                print(f"  Updated {count} rows")
            except Exception as e:
                print(f"  ERROR: {e}")

            # Rate limit
            if not dry_run and i < len(dates) - 1:
                await asyncio.sleep(0.5)

        print(
            f"\nBackfill complete. Total rows {'would be ' if dry_run else ''}updated: {total_updated}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Backfill foreign_flow_details with per-ticker data"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    asyncio.run(run_backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
