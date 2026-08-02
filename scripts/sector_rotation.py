#!/usr/bin/env python3
"""
Daily Sector Rotation Detection

Runs BEFORE daily scan to detect hot/cold sectors.
Uses yesterday's data (since today's scan hasn't run yet).
Saves result to PostgreSQL.
"""

import asyncio
import os
from datetime import datetime

from data.sector_rotation import run_sector_rotation
from shared.config import get_research_dir, get_scan_date
from shared.database import Database
from shared.neon import insert_sector_rotation
from shared.telegram import send_telegram_error


async def _main_async():
    today = get_scan_date()
    scan_date = datetime.strptime(today, "%Y-%m-%d").date()
    output_dir = get_research_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 50}")
    print(f"Sector Rotation Detection - {today}")
    print(f"{'=' * 50}\n")

    from shared.env import is_dry_run

    if not os.environ.get("OPENROUTER_API_KEY") and not is_dry_run():
        print("ERROR: OPENROUTER_API_KEY not set")
        return

    try:
        async with Database():
            rotation = await run_sector_rotation(output_dir.parent, output_dir)

            if await insert_sector_rotation(scan_date, rotation):
                print("  DB: sector rotation inserted")

        print(f"\n{'=' * 50}")
        print("Sector Rotation Results")
        print(f"{'=' * 50}")
        print(f"Hot sectors:  {rotation.get('hot_sectors', [])}")
        print(f"Cold sectors: {rotation.get('cold_sectors', [])}")
        print(f"Signal: {rotation.get('rotation_signal', '')}")
    except Exception as error:
        error_message = f"Sector rotation failed (non-blocking): {error}"
        print(f"WARN: {error_message}")
        send_telegram_error(error_message)
        raise


if __name__ == "__main__":
    asyncio.run(_main_async())
