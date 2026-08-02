"""Business logic for VN quarterly earnings calendar management.

Vietnamese filing deadlines (days after quarter end):
  Q1 (Jan-Mar)  → Apr 30  (30 days after Mar 31)
  Q2 (Apr-Jun)  → Jul 31
  Q3 (Jul-Sep)  → Oct 31
  Q4 (Oct-Dec)  → Jan 31 next year
  Annual        → Mar 31 (90 days after Dec 31)
"""

from __future__ import annotations

from datetime import date

from .neon.earnings import get_upcoming_earnings as _db_get_upcoming
from .neon.earnings import upsert_expected_dates

# ============================================================================
# Filing deadline computation
# ============================================================================

_QUARTER_DEADLINES: list[tuple[str, int, int]] = [
    # (label, month, day)
    ("Q1", 4, 30),
    ("Q2", 7, 31),
    ("Q3", 10, 31),
    ("Annual", 3, 31),  # annual filed same year+1 → handled in compute below
]


def compute_expected_filing_dates(year: int) -> list[dict]:
    """Return {fiscal_quarter, expected_date} for all 4 quarters + annual.

    Q4 deadline falls in next year (Jan 31). Annual deadline falls in next
    year (Mar 31). All other quarters fall within the same calendar year.

    Args:
        year: The fiscal year the quarters belong to.

    Returns:
        List of 5 dicts, each with keys: fiscal_quarter, expected_date.
    """
    results: list[dict] = [
        {"fiscal_quarter": f"Q1-{year}", "expected_date": date(year, 4, 30)},
        {"fiscal_quarter": f"Q2-{year}", "expected_date": date(year, 7, 31)},
        {"fiscal_quarter": f"Q3-{year}", "expected_date": date(year, 10, 31)},
        # Q4 and Annual deadlines fall in year+1
        {"fiscal_quarter": f"Q4-{year}", "expected_date": date(year + 1, 1, 31)},
        {"fiscal_quarter": f"Annual-{year}", "expected_date": date(year + 1, 3, 31)},
    ]
    return results


# ============================================================================
# Population helper
# ============================================================================


async def populate_earnings_calendar(tickers: list[str], year: int) -> int:
    """Bulk insert expected filing dates for given tickers and year.

    Upserts all 5 periods (Q1–Q4 + Annual) for each ticker.

    Args:
        tickers: List of ticker symbols.
        year: Fiscal year to populate.

    Returns:
        Total rows upserted.
    """
    if not tickers:
        return 0

    periods = compute_expected_filing_dates(year)
    rows: list[dict] = [
        {
            "ticker": ticker.upper(),
            "fiscal_quarter": period["fiscal_quarter"],
            "expected_date": period["expected_date"],
        }
        for ticker in tickers
        for period in periods
    ]

    count = await upsert_expected_dates(rows)
    return count


# ============================================================================
# Query facade (thin wrapper over DB layer)
# ============================================================================


async def get_upcoming_earnings(
    tickers: list[str] | None = None,
    lookahead_days: int = 30,
) -> list[dict]:
    """Get earnings filings expected within the lookahead window.

    Args:
        tickers: Optional list of tickers to filter. None = all tickers.
        lookahead_days: How many calendar days ahead to look.

    Returns:
        List of dicts with ticker, fiscal_quarter, expected_date, days_until.
    """
    return await _db_get_upcoming(tickers=tickers, lookahead_days=lookahead_days)
