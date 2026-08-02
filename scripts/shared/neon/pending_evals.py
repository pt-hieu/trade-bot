"""DB access for PENDING evaluation resolution.

Query PENDING evaluations and update their status after multi-day
price checks resolve them to WIN or LOSS.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..database import get_db


async def get_pending_evaluations(
    scan_date: date,
    lookback_days: int = 7,
) -> list[dict]:
    """Fetch PENDING evaluations from recent daily records.

    Joins with daily_recommendations to get entry/stop/target prices
    that are stored on the recommendation, not the evaluation.

    Args:
        scan_date: Pipeline scan date (avoids wall-clock dependency).
        lookback_days: How many calendar days back to search for PENDING evals.

    Returns:
        List of dicts with: id, ticker, record_date, entry_price_vnd,
        stop_price_vnd, target_price_vnd
    """
    db = await get_db()
    cutoff = scan_date - timedelta(days=lookback_days)

    rows = await db.fetch_all(
        """
        SELECT
            e.id,
            e.ticker,
            dr.record_date,
            r.entry_price_vnd,
            r.stop_price_vnd,
            r.target_price_vnd
        FROM daily_evaluations e
        JOIN daily_records dr ON dr.id = e.record_id
        JOIN daily_recommendations r
            ON r.record_id = e.record_id
            AND r.ticker = e.ticker
            AND r.action::text = e.recommendation::text
        WHERE e.status = 'PENDING'
            AND dr.record_date >= $1
        ORDER BY dr.record_date ASC
        """,
        cutoff,
    )
    return [dict(row) for row in rows]


async def batch_update_evaluation_status(
    resolutions: list[tuple[str, str, float]],
) -> None:
    """Batch-update resolved evaluations in a single transaction.

    Args:
        resolutions: List of (eval_id, new_status, pnl_percent) tuples.
    """
    if not resolutions:
        return

    db = await get_db()
    for eval_id, new_status, pnl_percent in resolutions:
        won = new_status == "WIN"
        target_hit = new_status == "WIN"
        stop_hit = new_status == "LOSS"

        await db.execute(
            """
            UPDATE daily_evaluations
            SET status = $2::eval_status,
                pnl_percent = $3,
                won = $4,
                target_hit = $5,
                stop_hit = $6
            WHERE id = $1
            """,
            eval_id,
            new_status,
            pnl_percent,
            won,
            target_hit,
            stop_hit,
        )
