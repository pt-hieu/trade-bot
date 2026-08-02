#!/usr/bin/env python3
"""
Daily Market Scan Script for Vietnamese Stock Trading

Runs at 7 AM Vietnam time via GitHub Actions.
Fetches price/technical data via vnstock.
Fetches articles via vnstock_news RSS feeds.
Saves raw data to research/YYYY-MM-DD/ for analysis via /intel command.
"""

import argparse
import asyncio
import os
from datetime import datetime, timedelta

from data.prices import fetch_prices_async
from data.technicals import fetch_technicals_async
from shared.config import PRICE_MULTIPLIER, get_scan_date
from shared.database import get_db
from shared.migration_guard import (
    MigrationDriftError,
    assert_no_pending_migrations,
    report_drift_and_exit,
)
from shared.neon import (
    get_portfolio_holdings,
    get_swing_watchlist,
    insert_daily_scan,
    update_portfolio_prices,
    update_swing_rsi_batch,
)
from shared.portfolio_invariants import (
    PortfolioInvariantError,
    assert_no_dual_listed_tickers,
    report_invariant_and_exit,
)
from shared.telegram import send_telegram_error
from shared.watchlist import merge_holdings_into_watchlist

TODAY = get_scan_date()
FORCE_RUN = os.environ.get("FORCE_RUN") == "true"


def _build_scan_summary(prices, technicals):
    """Build scan summary counts."""
    return {
        "scan_time": datetime.now().isoformat(),
        "scan_date": TODAY,
        "prices_fetched": len([p for p in prices.values() if "error" not in p]),
        "technicals_fetched": len([t for t in technicals.values() if "error" not in t]),
    }


async def _run_scan(watchlist: dict, holdings: list):
    """Core scan logic — runs inside shared database pool."""
    print(f"\n{'=' * 60}")
    print(f"Daily Market Scan - {TODAY}")
    print(f"{'=' * 60}\n")

    # Check LLM API key - required for query generation (skipped in dry-run)
    from shared.env import is_dry_run

    if not os.environ.get("OPENROUTER_API_KEY") and not is_dry_run():
        error_msg = (
            "OPENROUTER_API_KEY not set.\n\nCannot proceed without LLM for query generation."
        )
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        raise SystemExit(1)

    prices = {}
    technicals = {}

    scan_date = datetime.strptime(TODAY, "%Y-%m-%d").date()

    # Merge holdings into watchlist so portfolio positions get data too
    fetch_list = merge_holdings_into_watchlist(watchlist, holdings)

    # Add VN-Index for benchmark returns (Beta, Sharpe, Sortino)
    fetch_list["_benchmark"] = ["VNINDEX"]

    # Use day before scan_date so we always get yesterday's completed close,
    # even if the scan is re-run during market hours.
    price_end_date = (scan_date - timedelta(days=1)).strftime("%Y-%m-%d")

    prices, technicals = await asyncio.gather(
        fetch_prices_async(fetch_list, end_date=price_end_date),
        fetch_technicals_async(fetch_list, end_date=price_end_date),
    )

    # Update RSI in database
    if technicals:
        print("Updating RSI in database...")
        rsi_data = {
            ticker: data.get("rsi")
            for ticker, data in technicals.items()
            if "error" not in data and data.get("rsi") is not None
        }
        if rsi_data:
            updated = await update_swing_rsi_batch(rsi_data)
            print(f"  Updated {updated}/{len(rsi_data)} stocks")

    # Update portfolio prices in database
    # fetch_prices_async returns thousands VND from vnstock API; multiply to VND
    if prices and holdings:
        print("Updating portfolio prices in database...")
        held_tickers = {slice_row["ticker"] for slice_row in holdings if slice_row.get("ticker")}
        portfolio_prices = {
            ticker: data.get("close", 0) * PRICE_MULTIPLIER
            for ticker, data in prices.items()
            if ticker in held_tickers and "error" not in data
        }
        if portfolio_prices:
            updated = await update_portfolio_prices(portfolio_prices)
            print(f"  Updated {updated}/{len(portfolio_prices)} portfolio prices")

    # Save metadata
    metadata = _build_scan_summary(prices, technicals)

    # Insert data to database
    print("\nInserting data to database...")

    # Insert scan metadata
    await insert_daily_scan(
        scan_date,
        {
            "status": "success",
            "watchlist_count": sum(len(v) for v in watchlist.values()),
            "prices_fetched": metadata["prices_fetched"],
            "articles_count": 0,
        },
    )
    print("  Scan metadata: inserted")

    print(f"\n{'=' * 60}")
    print("Scan Complete!")
    print(f"  Prices: {metadata['prices_fetched']} stocks")
    print(f"  Technicals: {metadata['technicals_fetched']} stocks")

    print("  Database: data inserted")
    print(f"{'=' * 60}\n")


async def _check_already_ran_today(scan_date) -> bool:
    """Check if daily scan already ran for given date. Returns True if exists."""
    database = await get_db()
    row = await database.fetch_one(
        "SELECT scan_date FROM daily_scans WHERE scan_date = $1",
        scan_date,
    )
    return row is not None


async def _check_ran_cli():
    """CLI: print 'true'/'false' based on whether scan already ran today.

    Intentionally skips the migration drift guard — only reads daily_scans,
    which is migration-stable. Blocking this on drift would prevent the
    GH Actions dedup check from running while drift exists.
    """
    from shared.database import Database, close_db

    try:
        async with Database():
            scan_date = datetime.strptime(TODAY, "%Y-%m-%d").date()
            already_ran = await _check_already_ran_today(scan_date)
            print("true" if already_ran else "false", end="")
    finally:
        await close_db()


async def _mark_holiday_cli():
    """CLI: insert a 'holiday' record in daily_scans for today's scan date.

    Intentionally skips the migration drift guard — only writes daily_scans,
    which is migration-stable. Holiday registration must succeed even if
    other migrations are pending.
    """
    from shared.database import Database, close_db

    try:
        async with Database():
            scan_date = datetime.strptime(TODAY, "%Y-%m-%d").date()
            await insert_daily_scan(
                scan_date,
                {
                    "status": "holiday",
                    "watchlist_count": 0,
                    "prices_fetched": 0,
                    "articles_count": 0,
                },
            )
            print(f"Marked {scan_date} as holiday in daily_scans")
    finally:
        await close_db()


async def _main_async(force: bool = False):
    """Async entry point — single event loop, shared database pool."""
    from shared.database import Database, close_db

    try:
        async with Database():
            from shared.rules.scoring import validate_scoring_config
            from shared.trading_config import init_trading_config

            await assert_no_pending_migrations()
            await assert_no_dual_listed_tickers()
            await init_trading_config()
            from shared.rules.catalyst_override.geolabel import _validate_geo_factor_map_once

            await _validate_geo_factor_map_once()
            # SWI-171: Σw=1 + shape invariants for scoring.yaml. Crash startup
            # rather than silently scoring with a malformed weight vector.
            validate_scoring_config()

            watchlist, holdings = await asyncio.gather(
                get_swing_watchlist(), get_portfolio_holdings()
            )
            print(
                f"Loaded from database: "
                f"{sum(len(v) for v in watchlist.values())} watchlist stocks, "
                f"{len(holdings)} holdings"
            )
            await _run_scan(watchlist, holdings)
    except MigrationDriftError as drift:
        report_drift_and_exit(drift)
    except PortfolioInvariantError as exc:
        report_invariant_and_exit(exc)
    except Exception as e:
        error_msg = f"Daily scan failed: {e}"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        raise
    finally:
        await close_db()


def main():
    """Sync entry point."""
    parser = argparse.ArgumentParser(description="Daily Market Scan")
    parser.add_argument(
        "--force", action="store_true", help="Force re-run even if already ran today"
    )
    parser.add_argument(
        "--check", action="store_true", help="Check if already ran today (prints true/false)"
    )
    parser.add_argument(
        "--mark-holiday",
        action="store_true",
        help="Insert a holiday record in daily_scans for dedup",
    )
    args = parser.parse_args()

    if args.check:
        asyncio.run(_check_ran_cli())
        return

    if args.mark_holiday:
        asyncio.run(_mark_holiday_cli())
        return

    asyncio.run(_main_async(force=args.force or FORCE_RUN))


if __name__ == "__main__":
    main()
