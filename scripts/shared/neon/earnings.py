"""Earnings calendar DB queries for VN quarterly filing awareness."""

from datetime import date

from ..database import get_db


async def get_upcoming_earnings(
    tickers: list[str] | None,
    lookahead_days: int = 30,
) -> list[dict]:
    """Return upcoming earnings rows within lookahead window.

    Filters by ticker list if provided. Returns dicts with ticker,
    fiscal_quarter, expected_date, days_until (computed from today).
    """
    db = await get_db()

    if tickers:
        upper_tickers = [t.upper() for t in tickers]
        rows = await db.fetch_all(
            """
            SELECT
                ticker,
                fiscal_quarter,
                expected_date,
                (expected_date - CURRENT_DATE)::int AS days_until
            FROM earnings_calendar
            WHERE status = 'upcoming'
              AND expected_date BETWEEN CURRENT_DATE AND (CURRENT_DATE + $1::int)
              AND ticker = ANY($2::varchar[])
            ORDER BY expected_date ASC
            """,
            lookahead_days,
            upper_tickers,
        )
    else:
        rows = await db.fetch_all(
            """
            SELECT
                ticker,
                fiscal_quarter,
                expected_date,
                (expected_date - CURRENT_DATE)::int AS days_until
            FROM earnings_calendar
            WHERE status = 'upcoming'
              AND expected_date BETWEEN CURRENT_DATE AND (CURRENT_DATE + $1::int)
            ORDER BY expected_date ASC
            """,
            lookahead_days,
        )

    return [
        {
            "ticker": row["ticker"],
            "fiscal_quarter": row["fiscal_quarter"],
            "expected_date": row["expected_date"],
            "days_until": row["days_until"],
        }
        for row in rows
    ]


async def upsert_expected_dates(rows: list[dict]) -> int:
    """Bulk upsert earnings expected dates.

    Each row must have: ticker, fiscal_quarter, expected_date.
    Returns count of rows upserted.
    """
    if not rows:
        return 0

    db = await get_db()
    args_list = [
        (
            row["ticker"].upper(),
            row["fiscal_quarter"],
            row["expected_date"],
        )
        for row in rows
    ]

    await db.execute_many(
        """
        INSERT INTO earnings_calendar (ticker, fiscal_quarter, expected_date, status)
        VALUES ($1, $2, $3, 'upcoming')
        ON CONFLICT (ticker, fiscal_quarter)
        DO UPDATE SET
            expected_date = EXCLUDED.expected_date,
            updated_at = NOW()
        """,
        args_list,
    )
    return len(args_list)


async def mark_earnings_filed(
    ticker: str,
    fiscal_quarter: str,
    actual_date: date,
) -> None:
    """Mark an earnings row as filed with the actual filing date."""
    db = await get_db()
    await db.execute(
        """
        UPDATE earnings_calendar
        SET status = 'filed',
            actual_date = $3,
            updated_at = NOW()
        WHERE ticker = $1
          AND fiscal_quarter = $2
        """,
        ticker.upper(),
        fiscal_quarter,
        actual_date,
    )


async def save_pre_earnings_snapshot(
    ticker: str,
    fiscal_quarter: str,
    price_vnd: int | None,
    rsi: float | None,
    pe: float | None,
) -> None:
    """Save pre-earnings price/technical snapshot for post-filing analysis."""
    db = await get_db()
    await db.execute(
        """
        UPDATE earnings_calendar
        SET pre_price_vnd = $3,
            pre_rsi = $4,
            pre_pe = $5,
            updated_at = NOW()
        WHERE ticker = $1
          AND fiscal_quarter = $2
        """,
        ticker.upper(),
        fiscal_quarter,
        price_vnd,
        rsi,
        pe,
    )
