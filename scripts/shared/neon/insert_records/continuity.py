"""Day-over-day continuity update — backfills yesterday's next-day price change."""

from __future__ import annotations

from datetime import date

from ...database import get_db
from .._sync import make_sync


async def update_previous_day_change(today_date: date, today_vn_change_pct: float) -> bool:
    """Update yesterday's daily_record with today's VN-Index change."""
    db = await get_db()

    try:
        prev_record = await db.fetch_one(
            "SELECT id, record_date FROM daily_records WHERE record_date < $1 ORDER BY record_date DESC LIMIT 1",
            today_date,
        )

        if not prev_record:
            print(f"  [Neon] No previous day record found before {today_date}")
            return False

        await db.execute(
            "UPDATE daily_records SET next_day_change_pct = $1 WHERE id = $2",
            today_vn_change_pct,
            prev_record["id"],
        )

        print(
            f"  [Neon] Updated {prev_record['record_date']} next_day_change_pct = {today_vn_change_pct}%"
        )
        return True

    except Exception as e:
        print(f"  [Neon] Failed to update previous day change: {e}")
        return False


update_previous_day_change_sync = make_sync(update_previous_day_change)
