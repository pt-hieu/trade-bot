"""Insert functions for daily scan data."""

from datetime import date

from ..database import get_db
from ._sync import make_sync


async def insert_daily_scan(scan_date: date, metadata: dict) -> str:
    """Create or update daily_scans record. Returns scan_date string."""
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO daily_scans (scan_date, status, watchlist_count, prices_fetched, articles_count)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (scan_date) DO UPDATE SET
                status = EXCLUDED.status,
                watchlist_count = EXCLUDED.watchlist_count,
                prices_fetched = EXCLUDED.prices_fetched,
                articles_count = EXCLUDED.articles_count
            """,
            scan_date,
            metadata.get("status", "success"),
            metadata.get("watchlist_count"),
            metadata.get("prices_fetched"),
            metadata.get("articles_count"),
        )
        return str(scan_date)
    except Exception as e:
        print(f"  [Neon] Failed to insert daily scan: {e}")
        return ""


# ============================================================================
# Sync Wrappers
# ============================================================================

insert_daily_scan_sync = make_sync(insert_daily_scan)
