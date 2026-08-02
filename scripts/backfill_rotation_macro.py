#!/usr/bin/env python3
"""
One-off backfill: persist rotation and macro evaluations for historical daily_records.

Usage:
    SWINGY_ENV=production uv run python scripts/backfill_rotation_macro.py [--dry-run]
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents import evaluate_macro_for_day, evaluate_rotation_for_day
from retro.data import fetch_eod_prices
from shared.database import Database, get_db
from shared.neon.insert_evaluations import (
    insert_macro_evaluation,
    insert_rotation_evaluation,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

RESEARCH_DIR = Path(__file__).parent.parent / "research"


async def backfill():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done")
    parser.add_argument("--days", type=int, default=30, help="Days back to backfill")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-evaluate existing macro evaluations with current criteria "
        "(use when evaluation logic has changed, e.g., regime accuracy thresholds)",
    )
    args = parser.parse_args()

    async with Database():
        db = await get_db()

        since = date.today() - timedelta(days=args.days)
        records = await db.fetch_all(
            """SELECT id, record_date::text AS record_date
               FROM daily_records
               WHERE record_date >= $1
               ORDER BY record_date ASC""",
            since,
        )
        logger.info("Found %d daily_records since %s", len(records), since)

        # Find which already have evaluations
        existing_rotation = set()
        existing_macro = set()
        for record in records:
            rotation_exists = await db.fetch_val(
                "SELECT COUNT(*) FROM rotation_evaluations WHERE record_id = $1",
                record["id"],
            )
            if rotation_exists:
                existing_rotation.add(record["record_date"])

            macro_exists = await db.fetch_val(
                "SELECT COUNT(*) FROM macro_evaluations WHERE record_id = $1",
                record["id"],
            )
            if macro_exists:
                existing_macro.add(record["record_date"])

        if args.overwrite:
            # --overwrite: re-evaluate ALL records (delete + re-insert macro evals)
            records_to_backfill = records
            logger.info(
                "OVERWRITE mode: will re-evaluate %d records "
                "(%d have rotation, %d have macro — macro will be re-evaluated)",
                len(records_to_backfill),
                len(existing_rotation),
                len(existing_macro),
            )
        else:
            records_to_backfill = [
                record
                for record in records
                if record["record_date"] not in existing_rotation
                or record["record_date"] not in existing_macro
            ]
            logger.info(
                "Need backfill: %d records (%d already have rotation, %d already have macro)",
                len(records_to_backfill),
                len(existing_rotation),
                len(existing_macro),
            )

        if args.dry_run:
            for record in records_to_backfill:
                needs_rotation = record["record_date"] not in existing_rotation
                needs_macro = record["record_date"] not in existing_macro
                logger.info(
                    "  %s: rotation=%s macro=%s",
                    record["record_date"],
                    "NEED" if needs_rotation else "OK",
                    "NEED" if needs_macro else "OK",
                )
            return

        rotation_count = 0
        macro_count = 0
        for record in records_to_backfill:
            record_date = record["record_date"]
            record_id = record["id"]
            needs_rotation = record_date not in existing_rotation
            needs_macro = record_date not in existing_macro

            logger.info("Processing %s...", record_date)

            # Fetch EOD prices for this date
            try:
                eod_prices, _, _ = await fetch_eod_prices(record_date)
            except Exception as error:
                logger.warning("Failed to fetch EOD prices for %s: %s", record_date, error)
                continue

            if not eod_prices:
                logger.warning("No EOD prices for %s, skipping", record_date)
                continue

            # Evaluate and persist rotation
            if needs_rotation:
                try:
                    scan_date = date.fromisoformat(record_date)
                    rotation_eval = await evaluate_rotation_for_day(scan_date, eod_prices)
                    if rotation_eval:
                        await insert_rotation_evaluation(record_id, rotation_eval, db)
                        rotation_count += 1
                        logger.info("  Rotation: %s", rotation_eval.get("overall_accuracy"))
                    else:
                        logger.info("  Rotation: no data (no sector prediction for this date)")
                except Exception as error:
                    logger.warning("  Rotation failed: %s", error)

            # Evaluate and persist macro
            if args.overwrite and not needs_macro:
                # Delete existing macro eval so we can re-insert with new criteria
                try:
                    await db.execute(
                        "DELETE FROM macro_evaluations WHERE record_id = $1", record_id
                    )
                    needs_macro = True
                except Exception as error:
                    logger.warning("  Failed to delete existing macro eval: %s", error)

            if needs_macro:
                try:
                    scan_date = date.fromisoformat(record_date)
                    date_dir = RESEARCH_DIR / record_date
                    macro_eval = await evaluate_macro_for_day(
                        scan_date, eod_prices, date_dir=date_dir
                    )
                    if macro_eval:
                        await insert_macro_evaluation(record_id, macro_eval, db)
                        macro_count += 1
                        logger.info("  Macro: %s", macro_eval.get("global_risk_regime"))
                    else:
                        logger.info("  Macro: no data (no macro metrics for this date)")
                except Exception as error:
                    logger.warning("  Macro failed: %s", error)

        logger.info(
            "Backfill complete: %d rotation evals, %d macro evals inserted",
            rotation_count,
            macro_count,
        )


if __name__ == "__main__":
    asyncio.run(backfill())
