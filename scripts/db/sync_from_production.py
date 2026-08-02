#!/usr/bin/env python3
"""
Sync production Neon DB data to local Docker DB.

Dumps data from production (SWINGY_ENV=production) and restores to local Docker.
Schema must already exist locally (via docker-compose init).

Usage:
    # Sync all data
    uv run python scripts/db/sync_from_production.py

    # Sync only recent data (last N days of time-series tables)
    uv run python scripts/db/sync_from_production.py --days 30

    # Sync only specific tables
    uv run python scripts/db/sync_from_production.py --tables swing_watchlist,portfolio_holdings,goals

    # Dry run (show what would be synced)
    uv run python scripts/db/sync_from_production.py --dry-run
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Configuration ---

LOCAL_URL = "postgresql://swingy:localdev@localhost:5432/swingy"

# Reference/config tables — always sync fully
FULL_SYNC_TABLES = [
    "sectors",
    "swing_watchlist",
    "longterm_watchlist",
    "portfolio_holdings",
    "goals",
    "schema_migrations",
    # agent_prompts + agent_prompt_versions removed — config lives in YAML files.
    # For local web dev, run: uv run python scripts/db/sync_configs_to_db.py
]

# Time-series tables — sync last N days (keyed by date column)
TIMESERIES_TABLES = {
    "daily_scans": "scan_date",
    "market_regimes": "scan_date",
    "macro_metrics": "scan_date",
    "macro_events": "scan_date",
    "foreign_flows": "scan_date",
    "foreign_flow_details": "scan_date",
    "sector_rotations": "scan_date",
    "sector_rotation_details": "scan_date",
    "article_searches": "scan_date",
    "articles": "scan_date",
    "midday_checks": "scan_date",
    "midday_data": "scan_date",
    "midday_entries_hit": "scan_date",
    "midday_big_movers": "scan_date",
    "midday_position_alerts": "scan_date",
    "daily_records": "scan_date",
    "daily_recommendations": "scan_date",
    "daily_evaluations": "scan_date",
    "alerts": "created_at",
    "alert_history": "event_time",
}

# Learnings/patterns — always sync fully (small tables)
LEARNINGS_TABLES = [
    "learnings_summary",
    "learning_patterns",
    "sector_insights",
    "ticker_insights",
    "midday_patterns",
    "trading_mode_patterns",
    "rotation_patterns",
    "rotation_sector_scores",
    "macro_patterns",
    "macro_regime_accuracy",
    "macro_evaluations",
    "trading_rules",
]


def get_production_url() -> str:
    """Load production DATABASE_URL from .env."""
    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent.parent / ".env"
    if not env_path.exists():
        print("ERROR: .env file not found at project root")
        sys.exit(1)

    # Force-load .env to get production URL (override any existing value)
    load_dotenv(env_path, override=True)
    url = os.environ.get("DATABASE_URL", "")
    if not url or "neon.tech" not in url:
        print("ERROR: Could not load production DATABASE_URL from .env")
        print("Make sure .env has Neon connection string")
        sys.exit(1)
    # pg_dump needs direct connection, not pooler
    url = url.replace("-pooler", "")
    return url


def run_psql(local_url: str, sql: str, check: bool = True) -> subprocess.CompletedProcess:
    """Execute SQL against local DB."""
    return subprocess.run(
        ["psql", local_url, "-c", sql],
        check=check,
        capture_output=True,
        text=True,
    )


def sync_table_full(prod_url: str, local_url: str, table: str, dry_run: bool) -> int:
    """Sync entire table from production to local."""
    if dry_run:
        print(f"  [DRY] {table}: full sync")
        return 0

    # Dump from production
    dump = subprocess.run(
        ["pg_dump", prod_url, "--data-only", "--table", table, "--no-owner", "--no-privileges"],
        capture_output=True,
        text=True,
    )
    if dump.returncode != 0:
        print(f"  SKIP {table}: {dump.stderr.strip()[:100]}")
        return 0

    if not dump.stdout.strip():
        print(f"  SKIP {table}: empty")
        return 0

    # Truncate local + restore
    trunc = run_psql(local_url, f"TRUNCATE {table} CASCADE;", check=False)
    if trunc.returncode != 0:
        print(f"  SKIP {table}: truncate failed — {trunc.stderr.strip()[:80]}")
        return 0

    restore = subprocess.run(
        ["psql", local_url],
        input=dump.stdout,
        capture_output=True,
        text=True,
    )
    if restore.returncode != 0:
        print(f"  WARN {table}: {restore.stderr.strip()[:100]}")

    # Count rows
    result = subprocess.run(
        ["psql", local_url, "-t", "-c", f"SELECT count(*) FROM {table};"],
        capture_output=True,
        text=True,
    )
    count = result.stdout.strip()
    print(f"  OK   {table}: {count} rows")
    return int(count) if count.isdigit() else 0


def sync_table_recent(
    prod_url: str, local_url: str, table: str, date_col: str, days: int, dry_run: bool
) -> int:
    """Sync recent N days of a time-series table.

    Creates a temp view on production to filter by date, then pg_dump that view's
    data as INSERT statements. This avoids CSV escaping issues with JSONB/UUID columns.
    """
    if dry_run:
        print(f"  [DRY] {table}: last {days} days (by {date_col})")
        return 0

    # Step 1: Count rows in production for this date range
    count_sql = f"SELECT count(*) FROM {table} WHERE {date_col} >= NOW() - INTERVAL '{days} days'"
    count_result = subprocess.run(
        ["psql", prod_url, "-t", "-c", count_sql],
        capture_output=True,
        text=True,
    )
    if count_result.returncode != 0:
        # Date column might not work, fall back to full sync
        return sync_table_full(prod_url, local_url, table, dry_run)

    prod_count = count_result.stdout.strip()
    if prod_count == "0":
        print(f"  SKIP {table}: no recent data")
        return 0

    # Step 2: Dump filtered rows using COPY with binary-safe format
    # Use pg_dump with INSERT statements (handles all data types correctly)
    query = f"SELECT * FROM {table} WHERE {date_col} >= NOW() - INTERVAL '{days} days'"
    dump = subprocess.run(
        [
            "psql",
            prod_url,
            "-c",
            f"\\copy ({query}) TO STDOUT",
        ],
        capture_output=True,
        text=True,
    )
    if dump.returncode != 0 or not dump.stdout.strip():
        return sync_table_full(prod_url, local_url, table, dry_run)

    # Step 3: Truncate local + restore
    trunc = run_psql(local_url, f"TRUNCATE {table} CASCADE;", check=False)
    if trunc.returncode != 0:
        print(f"  SKIP {table}: truncate failed — {trunc.stderr.strip()[:80]}")
        return 0

    restore = subprocess.run(
        ["psql", local_url, "-c", f"\\copy {table} FROM STDIN"],
        input=dump.stdout,
        capture_output=True,
        text=True,
    )
    if restore.returncode != 0:
        print(f"  WARN {table}: copy failed, trying pg_dump fallback")
        return sync_table_full(prod_url, local_url, table, dry_run)

    result = subprocess.run(
        ["psql", local_url, "-t", "-c", f"SELECT count(*) FROM {table};"],
        capture_output=True,
        text=True,
    )
    count = result.stdout.strip()
    print(f"  OK   {table}: {count} rows (last {days} days)")
    return int(count) if count.isdigit() else 0


def main():
    parser = argparse.ArgumentParser(description="Sync production Neon DB to local Docker DB")
    parser.add_argument(
        "--days", type=int, default=30, help="Days of time-series data (default: 30)"
    )
    parser.add_argument("--tables", type=str, help="Comma-separated table names to sync")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced")
    args = parser.parse_args()

    prod_url = get_production_url()
    local_url = LOCAL_URL

    # Verify local DB is reachable
    try:
        subprocess.run(
            ["psql", local_url, "-c", "SELECT 1;"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: Local DB not reachable. Run: docker-compose up -d")
        sys.exit(1)

    print(f"Syncing production → local (last {args.days} days for time-series)")
    print(f"{'[DRY RUN]' if args.dry_run else ''}")
    print()

    # Filter tables if specified
    filter_tables = set(args.tables.split(",")) if args.tables else None

    # Disable FK constraints during sync
    if not args.dry_run:
        run_psql(local_url, "SET session_replication_role = 'replica';")

    total_rows = 0

    # 1. Full sync tables
    print("=== Reference tables (full sync) ===")
    for table in FULL_SYNC_TABLES:
        if filter_tables and table not in filter_tables:
            continue
        total_rows += sync_table_full(prod_url, local_url, table, args.dry_run)

    # 2. Time-series tables
    print(f"\n=== Time-series tables (last {args.days} days) ===")
    for table, date_col in TIMESERIES_TABLES.items():
        if filter_tables and table not in filter_tables:
            continue
        total_rows += sync_table_recent(
            prod_url, local_url, table, date_col, args.days, args.dry_run
        )

    # 3. Learnings tables
    print("\n=== Learnings tables (full sync) ===")
    for table in LEARNINGS_TABLES:
        if filter_tables and table not in filter_tables:
            continue
        total_rows += sync_table_full(prod_url, local_url, table, args.dry_run)

    # Re-enable FK constraints
    if not args.dry_run:
        run_psql(local_url, "SET session_replication_role = 'origin';")

    print(f"\nDone. Total rows synced: {total_rows}")


if __name__ == "__main__":
    main()
