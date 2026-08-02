#!/usr/bin/env python3
"""
Backfill embeddings for historical daily_records and learning_patterns.

Usage:
    cd scripts && uv run python db/backfill_embeddings.py
    cd scripts && uv run python db/backfill_embeddings.py --since 2026-01-15
"""

import argparse
import asyncio
import os
import sys
from datetime import date, datetime

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.env import load_env

load_env()

from agents.memory.embeddings import embed_context
from shared.database import Database, close_db


async def get_daily_records_for_backfill(since_date: date) -> list[dict]:
    """Get daily records with rotation and macro data for embedding."""
    from shared.database import Database

    pool = Database._pool
    if pool is None:
        raise RuntimeError("Database not connected")

    query = """
    SELECT
        dr.id,
        dr.record_date,
        dr.market_regime,
        dr.trading_mode,
        dr.win_rate,
        dr.key_insight,
        dr.context_embedding IS NOT NULL as has_embedding,
        re.hot_avg_return,
        re.cold_avg_return,
        re.market_avg_return,
        me.global_risk_regime,
        me.vix_value
    FROM daily_records dr
    LEFT JOIN rotation_evaluations re ON re.record_id = dr.id
    LEFT JOIN macro_evaluations me ON me.record_id = dr.id
    WHERE dr.record_date >= $1
    ORDER BY dr.record_date
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, since_date)
        return [dict(r) for r in rows]


async def get_rotation_sectors(record_id: str) -> tuple[list[str], list[str]]:
    """Get hot and cold sectors for a daily record."""
    from shared.database import Database

    pool = Database._pool
    if pool is None:
        raise RuntimeError("Database not connected")

    query = """
    SELECT
        s.name as sector_name,
        rsr.return_pct
    FROM rotation_sector_returns rsr
    JOIN rotation_evaluations re ON re.id = rsr.rotation_eval_id
    JOIN sectors s ON s.id = rsr.sector_id
    WHERE re.record_id = $1
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, record_id)

    if not rows:
        return [], []

    # Calculate market average
    returns = [float(r["return_pct"]) for r in rows if r["return_pct"] is not None]
    if not returns:
        return [], []

    market_avg = sum(returns) / len(returns)

    hot = []
    cold = []
    for row in rows:
        if row["return_pct"] is None:
            continue
        ret = float(row["return_pct"])
        if ret > market_avg + 0.5:  # At least 0.5% above average
            hot.append(row["sector_name"])
        elif ret < market_avg - 0.5:  # At least 0.5% below average
            cold.append(row["sector_name"])

    return hot, cold


async def get_learning_patterns_for_backfill() -> list[dict]:
    """Get learning patterns for embedding."""
    from shared.database import Database

    pool = Database._pool
    if pool is None:
        raise RuntimeError("Database not connected")

    query = """
    SELECT
        id,
        pattern_type,
        pattern_description,
        win_rate,
        loss_rate,
        sample_size,
        actionable_rule,
        avoid_rule,
        pattern_embedding IS NOT NULL as has_embedding
    FROM learning_patterns
    ORDER BY created_at
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        return [dict(r) for r in rows]


async def update_daily_embedding(record_date: date, embedding: list[float]) -> bool:
    """Update context embedding for a daily record."""
    from shared.database import Database

    pool = Database._pool
    if pool is None:
        raise RuntimeError("Database not connected")

    query = """
    UPDATE daily_records
    SET context_embedding = $2::vector
    WHERE record_date = $1
    """

    async with pool.acquire() as conn:
        await conn.execute(query, record_date, str(embedding))
        return True


async def update_pattern_embedding(pattern_id: str, embedding: list[float]) -> bool:
    """Update pattern embedding for a learning pattern."""
    import uuid

    from shared.database import Database

    pool = Database._pool
    if pool is None:
        raise RuntimeError("Database not connected")

    query = """
    UPDATE learning_patterns
    SET pattern_embedding = $2::vector
    WHERE id = $1
    """

    async with pool.acquire() as conn:
        await conn.execute(query, uuid.UUID(pattern_id), str(embedding))
        return True


async def backfill_daily_records(since_date: date, force: bool = False) -> int:
    """Backfill embeddings for daily records."""
    print(f"\n📅 Fetching daily records since {since_date}...")
    records = await get_daily_records_for_backfill(since_date)
    print(f"   Found {len(records)} records")

    updated = 0
    for record in records:
        record_date = record["record_date"]

        # Skip if already has embedding (unless force)
        if record["has_embedding"] and not force:
            print(f"   ⏭️  {record_date} - already has embedding, skipping")
            continue

        # Get hot/cold sectors
        hot_sectors, cold_sectors = await get_rotation_sectors(str(record["id"]))

        # Build context for embedding
        context = {
            "market_regime": record["market_regime"],
            "trading_mode": record["trading_mode"],
            "hot_sectors": hot_sectors,
            "cold_sectors": cold_sectors,
            "vix": float(record["vix_value"]) if record["vix_value"] else None,
            "global_macro": record["global_risk_regime"],
        }

        print(
            f"   🔄 {record_date} - {context['market_regime']}, hot={hot_sectors}, cold={cold_sectors}"
        )

        # Generate embedding
        embedding = embed_context(context)
        if embedding is None:
            print(f"   ⚠ {record_date} - embedding generation failed, skipping")
            continue

        # Update record
        await update_daily_embedding(record_date, embedding)
        updated += 1
        print(f"   ✓ {record_date} - embedding added ({len(embedding)} dims)")

    return updated


async def backfill_learning_patterns(force: bool = False) -> int:
    """Backfill embeddings for learning patterns."""
    print("\n📚 Fetching learning patterns...")
    patterns = await get_learning_patterns_for_backfill()
    print(f"   Found {len(patterns)} patterns")

    updated = 0
    for pattern in patterns:
        pattern_id = str(pattern["id"])

        # Skip if already has embedding (unless force)
        if pattern["has_embedding"] and not force:
            print(
                f"   ⏭️  {pattern['pattern_type']}: {pattern['pattern_description'][:50]}... - skipping"
            )
            continue

        # Build context for embedding
        context = {
            "pattern": pattern["pattern_description"],
            "pattern_type": pattern["pattern_type"],
            "win_rate": float(pattern["win_rate"]) if pattern["win_rate"] else 0,
        }

        print(f"   🔄 {pattern['pattern_type']}: {pattern['pattern_description'][:50]}...")

        # Generate embedding
        embedding = embed_context(context)
        if embedding is None:
            print(f"   ⚠ {pattern['pattern_type']}: embedding generation failed, skipping")
            continue

        # Update pattern
        await update_pattern_embedding(pattern_id, embedding)
        updated += 1
        print("   ✓ embedding added")

    return updated


async def main():
    parser = argparse.ArgumentParser(description="Backfill embeddings for memory system")
    parser.add_argument(
        "--since",
        type=str,
        default="2026-01-15",
        help="Start date for backfill (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing embeddings",
    )
    parser.add_argument(
        "--daily-only",
        action="store_true",
        help="Only backfill daily records",
    )
    parser.add_argument(
        "--patterns-only",
        action="store_true",
        help="Only backfill learning patterns",
    )

    args = parser.parse_args()
    since_date = datetime.strptime(args.since, "%Y-%m-%d").date()

    print("🚀 Embedding Backfill")
    print("=" * 50)

    async with Database():
        try:
            daily_count = 0
            pattern_count = 0

            if not args.patterns_only:
                daily_count = await backfill_daily_records(since_date, args.force)

            if not args.daily_only:
                pattern_count = await backfill_learning_patterns(args.force)

            print("\n" + "=" * 50)
            print("✅ Backfill Complete!")
            print(f"   Daily records updated: {daily_count}")
            print(f"   Patterns updated: {pattern_count}")

        finally:
            await close_db()


if __name__ == "__main__":
    asyncio.run(main())
