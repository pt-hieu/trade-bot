"""Ensemble vote history queries."""

from datetime import date, timedelta

from ..database import get_db


async def get_ensemble_vote_history(ticker: str, days_back: int = 7) -> list[dict]:
    """Get historical ensemble analyst votes for a ticker.

    Args:
        ticker: Stock ticker
        days_back: How many days to look back

    Returns:
        List of vote dicts: record_date, analyst_type, action, confidence, counter_thesis
    """
    db = await get_db()
    cutoff = date.today() - timedelta(days=days_back)
    rows = await db.fetch_all(
        """
        SELECT record_date, analyst_type, action, confidence, reasoning, counter_thesis
        FROM position_ensemble_votes
        WHERE ticker = $1 AND record_date >= $2
        ORDER BY record_date DESC, analyst_type
        """,
        ticker.upper(),
        cutoff,
    )
    return [dict(r) for r in rows] if rows else []


async def get_ensemble_vote_history_batch(
    tickers: list[str], days_back: int = 7
) -> dict[str, list[dict]]:
    """Get historical ensemble analyst votes for a batch of tickers in one query.

    Returns dict mapping uppercased ticker to a list of vote dicts ordered by
    record_date DESC, analyst_type ASC. Missing tickers map to empty lists.
    """
    if not tickers:
        return {}

    normalized = [ticker.upper() for ticker in tickers]
    db = await get_db()
    cutoff = date.today() - timedelta(days=days_back)
    rows = await db.fetch_all(
        """
        SELECT ticker, record_date, analyst_type, action, confidence,
               reasoning, counter_thesis
        FROM position_ensemble_votes
        WHERE ticker = ANY($1::text[]) AND record_date >= $2
        ORDER BY ticker, record_date DESC, analyst_type
        """,
        normalized,
        cutoff,
    )
    result: dict[str, list[dict]] = {ticker: [] for ticker in normalized}
    for row in rows:
        ticker_key = row["ticker"]
        result[ticker_key].append(
            {
                "record_date": row["record_date"],
                "analyst_type": row["analyst_type"],
                "action": row["action"],
                "confidence": row["confidence"],
                "reasoning": row["reasoning"],
                "counter_thesis": row["counter_thesis"],
            }
        )
    return result
