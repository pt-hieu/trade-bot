"""Weekly enrichment: earnings calendar refresh.

Populates expected earnings filing dates for watchlist + holdings tickers.
Called by weekly-enrichment GH Actions workflow.

Note: insider transactions and corporate events previously refreshed here are
now read directly from the vnstock API (shared.api.enrichment) — no DB caching needed.
"""

import asyncio


async def refresh_earnings_calendar(tickers: list[str]) -> int:
    """Populate/refresh earnings calendar for the current and next year.

    Inserts expected filing dates based on VN regulatory windows.
    Idempotent — uses ON CONFLICT DO NOTHING.
    """
    from datetime import date

    from shared.earnings_calendar import populate_earnings_calendar

    year = date.today().year
    count = await populate_earnings_calendar(tickers, year)
    # Also seed next year's dates if we're in Q4
    if date.today().month >= 10:
        count += await populate_earnings_calendar(tickers, year + 1)
    print(f"  Earnings calendar: {count} rows upserted")
    return count


async def _main_async():
    """Weekly earnings calendar refresh entry point."""
    from shared.database import Database, close_db
    from shared.neon import get_portfolio_holdings, get_swing_watchlist

    print("\n=== Weekly Earnings Calendar Refresh ===\n")

    async with Database():
        watchlist = await get_swing_watchlist()
        holdings = await get_portfolio_holdings()

        tickers_set: set[str] = set()
        for sector_tickers in watchlist.values():
            tickers_set.update(sector_tickers)
        tickers_set.update(slice_row["ticker"] for slice_row in holdings if slice_row.get("ticker"))
        tickers = sorted(tickers_set - {"VNINDEX"})

        print(f"Refreshing earnings calendar for {len(tickers)} tickers...")
        earnings_count = await refresh_earnings_calendar(tickers)
        print(f"\nDone: {earnings_count} rows upserted")

    await close_db()


if __name__ == "__main__":
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from shared.env import load_env

    load_env()

    asyncio.run(_main_async())
