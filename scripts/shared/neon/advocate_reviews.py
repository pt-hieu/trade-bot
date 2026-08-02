"""Advocate review persistence — store bull/bear stress-test results."""

import logging
from datetime import date

from ..database import get_db

logger = logging.getLogger(__name__)


async def insert_advocate_reviews(
    record_date: date,
    reviews: dict[str, list[dict]],
) -> int:
    """Persist advocate reviews to DB for audit trail.

    Idempotent: deletes existing reviews for same date before inserting.

    Args:
        record_date: Trading date being analyzed
        reviews: {"bull": [review_dicts], "bear": [review_dicts]}

    Returns:
        Number of rows inserted.
    """
    bull_reviews = reviews.get("bull") or []
    bear_reviews = reviews.get("bear") or []

    if not bull_reviews and not bear_reviews:
        return 0

    db = await get_db()
    try:
        async with db.transaction() as conn:
            # Idempotent: clear existing reviews for this date
            await conn.execute(
                "DELETE FROM advocate_reviews WHERE record_date = $1",
                record_date,
            )

            inserted = 0
            for reviewer_type, review_list in [("bull", bull_reviews), ("bear", bear_reviews)]:
                for review in review_list:
                    ticker = review.get("ticker")
                    if not ticker:
                        continue

                    await conn.execute(
                        """
                        INSERT INTO advocate_reviews
                            (record_date, ticker, reviewer_type, verdict,
                             confidence, key_arguments, blind_spots)
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb)
                        """,
                        record_date,
                        ticker,
                        reviewer_type,
                        review.get("verdict") or "MIXED",
                        review.get("confidence") or 0,
                        review.get("key_arguments") or [],
                        review.get("blind_spots") or [],
                    )
                    inserted += 1

        logger.info(
            "Persisted %d advocate reviews for %s (bull=%d, bear=%d)",
            inserted,
            record_date,
            len(bull_reviews),
            len(bear_reviews),
        )
        return inserted

    except Exception as e:
        logger.warning("Failed to persist advocate reviews for %s: %s", record_date, e)
        return 0
