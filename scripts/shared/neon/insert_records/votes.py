"""Position ensemble analyst votes insert for audit trail.

`execute_many` here is not transactional — see `daily.py` module docstring for
the shared non-atomicity invariant.
"""

from __future__ import annotations

from datetime import date

from ...database import get_db


async def insert_ensemble_votes(
    scan_date: date,
    votes: list[dict],
) -> bool:
    """Insert position ensemble analyst votes for audit trail.

    Args:
        scan_date: Date of the analysis
        votes: List of dicts with keys: ticker, analyst_type, action, confidence, reasoning
    """
    if not votes:
        return True

    db = await get_db()
    try:
        # Clear existing votes for this date (idempotent re-run)
        await db.execute(
            "DELETE FROM position_ensemble_votes WHERE record_date = $1",
            scan_date,
        )

        vote_rows = [
            (
                scan_date,
                vote["ticker"],
                vote["analyst_type"],
                vote["action"],
                vote.get("confidence") or 5,
                vote.get("reasoning"),
                vote.get("counter_thesis") or None,
            )
            for vote in votes
        ]
        await db.execute_many(
            """
            INSERT INTO position_ensemble_votes
                (record_date, ticker, analyst_type, action, confidence, reasoning, counter_thesis)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            vote_rows,
        )

        print(f"  [Neon] Inserted {len(votes)} ensemble votes for {scan_date}")
        return True
    except Exception as e:
        print(f"  [Neon] Failed to insert ensemble votes: {e}")
        return False
