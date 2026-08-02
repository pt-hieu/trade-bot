#!/usr/bin/env python3
"""Fetch current prices for watchlist stocks via vnstock API."""

import asyncio
from datetime import datetime, timedelta

from shared.vnstock_client import fetch_history_batch

# Fallback watchlist (used if database unavailable)
FALLBACK_WATCHLIST = [
    "FPT",
    "VHM",
    "NLG",
    "TCB",
    "VIX",
    "DXS",
    "MWG",
    "HPG",
    "SSI",
    "KBC",
    "GAS",
    "IDC",
    "VCB",
    "VIC",
    "MSN",
    "SAB",
    "VNM",
    "PVT",
    "PLX",
    "PVI",
    "BCM",
    "SZC",
    "KDH",
    "CTG",
    "TPB",
    "BID",
    "POW",
    "GVR",
    "HVN",
    "BVH",
]

# Try to load watchlist from database
WATCHLIST = FALLBACK_WATCHLIST
try:
    from shared.neon import get_swing_watchlist_sync

    sectors = get_swing_watchlist_sync()
    WATCHLIST = [ticker for tickers in sectors.values() for ticker in tickers]
    print(f"Loaded {len(WATCHLIST)} stocks from database")
except Exception as e:
    print(f"Database unavailable ({e}), using fallback watchlist")


async def main_async():
    print(f"\n{'Stock':<6} {'Price':>10} {'Change':>8} {'Volume':>12}")
    print("-" * 40)

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

    results = await fetch_history_batch(
        symbols=WATCHLIST,
        source="VCI",
        start=start,
        end=end,
        interval="1D",
    )

    for symbol in WATCHLIST:
        try:
            data = results.get(symbol, {})
            if "error" in data:
                print(f"{symbol:<6} Error: {data['error']}")
                continue

            records = data.get("data", [])
            if len(records) >= 2:
                latest = records[-1]
                prev = records[-2]
                change = ((latest["close"] - prev["close"]) / prev["close"]) * 100
                print(
                    f"{symbol:<6} {latest['close']:>10,.0f} {change:>+7.1f}% {latest['volume']:>12,.0f}"
                )
            elif records:
                latest = records[-1]
                print(
                    f"{symbol:<6} {latest['close']:>10,.0f} {'N/A':>8} {latest['volume']:>12,.0f}"
                )
            else:
                print(f"{symbol:<6} No data")
        except Exception as e:
            print(f"{symbol:<6} Error: {e}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
