"""
Price fetching via vnstock API server.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from shared.vnstock_client import fetch_history_batch

logger = logging.getLogger(__name__)


async def fetch_prices_async(watchlist: dict, end_date: str | None = None) -> dict:
    """
    Fetch EOD prices for watchlist stocks via vnstock API.

    Args:
        watchlist: Dict of sector -> list of tickers
        end_date: Last date to fetch (YYYY-MM-DD). Defaults to yesterday in Vietnam TZ
                  so callers always get completed bars, never partial intraday bars.
                  Pass explicit date to override (e.g. midday wants today's live bar).

    Returns:
        Dict of ticker -> price data
    """
    from shared.config import get_yesterday_date

    print("Fetching prices via vnstock API...")

    all_stocks = []
    for tickers in watchlist.values():
        all_stocks.extend(tickers)

    if end_date is None:
        end_date = get_yesterday_date()
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")

    try:
        results = await fetch_history_batch(
            symbols=all_stocks,
            source="VCI",
            start=start_date,
            end=end_date,
            interval="1D",
        )

        prices_data = {}
        for symbol, data in results.items():
            if "error" in data:
                print(f"  {symbol}: Error - {data['error']}")
                prices_data[symbol] = {"error": data["error"]}
            elif data.get("data"):
                bars = data["data"]
                latest = bars[-1]
                prev = bars[-2] if len(bars) >= 2 else None
                close = float(latest.get("close") or 0)
                prev_close = float(prev.get("close") or 0) if prev else None
                change_pct = (
                    round((close - prev_close) / prev_close * 100, 2) if prev_close else None
                )
                prices_data[symbol] = {
                    "date": str(latest.get("time") or ""),
                    "open": float(latest.get("open") or 0),
                    "high": float(latest.get("high") or 0),
                    "low": float(latest.get("low") or 0),
                    "close": close,
                    "volume": int(latest.get("volume") or 0),
                    "prev_close": prev_close,
                    "change_pct": change_pct,
                }
                print(f"  {symbol}: {prices_data[symbol]['close']}")
            else:
                print(f"  {symbol}: No data")
                prices_data[symbol] = {"error": "No data"}

        return prices_data

    except Exception as e:
        logger.warning(
            "fetch_prices_async failed for %d tickers (%s): %s",
            len(all_stocks),
            ", ".join(all_stocks[:10]),
            e,
        )
        return {}


def fetch_prices(watchlist: dict, end_date: str | None = None) -> dict:
    """Sync wrapper for fetch_prices_async."""
    return asyncio.run(fetch_prices_async(watchlist, end_date=end_date))
