"""
vnstock stress test - verify connection reuse and data freshness.
"""

import time
from datetime import datetime, timedelta

# Import shared first to register API key
import shared  # noqa: F401


def main():
    from vnstock import Quote

    # All 27 watchlist tickers
    TICKERS = [
        "ACB",
        "BID",
        "CTG",
        "HDB",
        "MBB",
        "SHB",
        "TCB",
        "TPB",
        "VCB",
        "VIB",
        "VPB",
        "MSN",
        "VIC",
        "GAS",
        "GVR",
        "HPG",
        "PVI",
        "PVT",
        "SAB",
        "VNM",
        "VHM",
        "BVH",
        "POW",
        "FPT",
        "MWG",
        "SSI",
        "VIX",
    ]

    print(f"Testing vnstock_data fetch at {datetime.now()}")
    print(f"Fetching {len(TICKERS)} tickers...\n")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

    results = {"success": [], "failed": [], "dates": {}, "prices": {}}
    start_time = time.time()

    for i, ticker in enumerate(TICKERS, 1):
        ticker_start = time.time()
        try:
            quote = Quote(source="VCI", symbol=ticker)
            df = quote.history(start=start_date, end=end_date, interval="1D")

            if not df.empty:
                latest = df.iloc[-1]
                date_str = str(latest.get("time", latest.name))[:10]
                close = float(latest.get("close", 0))
                elapsed = time.time() - ticker_start

                results["success"].append(ticker)
                results["dates"][ticker] = date_str
                results["prices"][ticker] = close
                print(
                    f"  [{i:2}/{len(TICKERS)}] {ticker}: {close:,.0f} ({date_str}) - {elapsed:.1f}s"
                )
            else:
                results["failed"].append(ticker)
                print(f"  [{i:2}/{len(TICKERS)}] {ticker}: EMPTY DATA")

        except Exception as e:
            results["failed"].append(ticker)
            elapsed = time.time() - ticker_start
            print(f"  [{i:2}/{len(TICKERS)}] {ticker}: ERROR - {str(e)[:50]} - {elapsed:.1f}s")

    total_time = time.time() - start_time

    print(f"\n{'=' * 50}")
    print("RESULTS")
    print(f"{'=' * 50}")
    print(f"Success: {len(results['success'])}/{len(TICKERS)}")
    print(f"Failed:  {len(results['failed'])}/{len(TICKERS)}")
    print(f"Total time: {total_time:.1f}s")

    if results["failed"]:
        print(f"\nFailed tickers: {', '.join(results['failed'])}")

    # Check for stale data
    unique_dates = set(results["dates"].values())
    print(f"\nData dates: {unique_dates}")

    today = datetime.now().strftime("%Y-%m-%d")
    if len(unique_dates) == 1:
        only_date = list(unique_dates)[0]
        if only_date != today:
            print(f"WARNING: All data from {only_date}, not today ({today})!")

    # Show VHM specifically (the problematic ticker)
    if "VHM" in results["prices"]:
        print(
            f"\nVHM check: {results['prices']['VHM']:,.0f} ({results['dates'].get('VHM', 'N/A')})"
        )


if __name__ == "__main__":
    main()
