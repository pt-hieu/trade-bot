"""Alert lifecycle management — cancel, cleanup, cap operations."""

from datetime import UTC, date, datetime

from ..database import get_db


async def cancel_stale_alerts(before_date: date) -> int:
    """Cancel stale alerts from before the given date.

    Respects expires_at for multi-day alerts (trailing stops, dip-buys):
    alerts with a future expires_at survive across days.
    """
    db = await get_db()
    now = datetime.now(UTC)
    result = await db.execute(
        """UPDATE alerts SET status = 'cancelled', updated_at = $1
           WHERE status = 'active'
             AND source_date < $2
             AND (expires_at IS NULL OR expires_at < $1)""",
        now,
        before_date,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


async def cancel_alerts_for_date(source_date: date) -> int:
    """Cancel active alerts for a given source date (re-run cleanup). Returns count."""
    db = await get_db()
    now = datetime.now(UTC)
    result = await db.execute(
        """UPDATE alerts SET status = 'cancelled', updated_at = $1
           WHERE status = 'active' AND source_date = $2""",
        now,
        source_date,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


async def cancel_alerts_by_source(
    source_date: date,
    sources: list[str],
) -> int:
    """Cancel active alerts for a date, filtered by source.

    Only cancels alerts from specified sources (e.g. morning_brief, catalyst_revision).
    Preserves trailing stops, position directives, and other sources.
    """
    if not sources:
        return 0
    db = await get_db()
    now = datetime.now(UTC)
    placeholders = ", ".join(f"${i + 3}" for i in range(len(sources)))
    result = await db.execute(
        f"""UPDATE alerts SET status = 'cancelled', updated_at = $1
            WHERE status = 'active'
              AND source_date = $2
              AND source IN ({placeholders})""",
        now,
        source_date,
        *sources,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


async def cancel_alerts_for_tickers(tickers: list[str]) -> int:
    """Cancel ALL active alerts for specific tickers. Returns count."""
    if not tickers:
        return 0
    db = await get_db()
    now = datetime.now(UTC)
    upper_tickers = [t.upper() for t in tickers]
    placeholders = ", ".join(f"${i + 2}" for i in range(len(upper_tickers)))
    result = await db.execute(
        f"""UPDATE alerts SET status = 'cancelled', updated_at = $1
            WHERE status = 'active'
            AND ticker IN ({placeholders})""",
        now,
        *upper_tickers,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


async def cleanup_orphan_alerts(scan_date: date, valid_tickers: set[str]) -> int:
    """Cancel alerts for tickers not in recommendations or holdings. Returns count."""
    if not valid_tickers:
        return 0
    db = await get_db()
    now = datetime.now(UTC)
    upper_tickers = sorted(t.upper() for t in valid_tickers)
    placeholders = ", ".join(f"${i + 3}" for i in range(len(upper_tickers)))
    result = await db.execute(
        f"""UPDATE alerts SET status = 'cancelled', updated_at = $1
            WHERE status = 'active' AND source_date = $2
            AND ticker NOT IN ({placeholders})""",
        now,
        scan_date,
        *upper_tickers,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


async def cap_daily_alerts(scan_date: date, max_alerts: int = 15) -> int:
    """Cancel lowest-priority alerts if daily count exceeds max. Returns count cancelled."""
    db = await get_db()
    count_rows = await db.fetch_all(
        "SELECT COUNT(*) as cnt FROM alerts WHERE source_date = $1 AND status = 'active'",
        scan_date,
    )
    total = int(count_rows[0]["cnt"]) if count_rows else 0
    if total <= max_alerts:
        return 0

    excess = total - max_alerts
    result = await db.execute(
        """
        UPDATE alerts SET status = 'cancelled', updated_at = NOW()
        WHERE id IN (
            SELECT id FROM alerts
            WHERE source_date = $1 AND status = 'active'
            ORDER BY
                CASE priority WHEN 'low' THEN 1 WHEN 'normal' THEN 2 WHEN 'high' THEN 3 ELSE 4 END ASC,
                created_at ASC
            LIMIT $2
        )
        """,
        scan_date,
        excess,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0
