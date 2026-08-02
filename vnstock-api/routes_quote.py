"""Quote and listing route handlers — /quote/* and /listing/* endpoints."""

import gc
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Query


def register_quote_routes(app, verify_api_key):
    @app.get("/quote/history")
    def quote_history(
        symbol: str,
        source: str = "VCI",
        start: str = None,
        end: str = None,
        interval: str = "1D",
        x_api_key: str = Header(None),
    ):
        """Fetch price history for a single symbol."""
        verify_api_key(x_api_key)
        from vnstock_data import Quote

        if not start:
            start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")

        try:
            quote = Quote(source=source, symbol=symbol)
            df = quote.history(start=start, end=end, interval=interval)

            # Convert timestamps to ISO format strings
            data = df.to_dict(orient="records")
            for row in data:
                if "time" in row and hasattr(row["time"], "isoformat"):
                    row["time"] = row["time"].isoformat()

            return {"symbol": symbol, "data": data, "count": len(df)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get("/quote/history/batch")
    def quote_history_batch(
        symbols: str = Query(..., description="Comma-separated symbols"),
        source: str = "VCI",
        start: str = None,
        end: str = None,
        interval: str = "1D",
        x_api_key: str = Header(None),
    ):
        """Fetch price history for multiple symbols."""
        verify_api_key(x_api_key)
        from vnstock_data import Quote

        if not start:
            start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")

        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        results = {}

        for symbol in symbol_list:
            quote = None
            df = None
            try:
                quote = Quote(source=source, symbol=symbol)
                df = quote.history(start=start, end=end, interval=interval)

                # Convert timestamps to ISO format strings
                data = df.to_dict(orient="records")
                for row in data:
                    if "time" in row and hasattr(row["time"], "isoformat"):
                        row["time"] = row["time"].isoformat()

                results[symbol] = {"data": data, "count": len(data)}
            except Exception as e:
                results[symbol] = {"error": str(e)}
            finally:
                # Free memory after each symbol to prevent OOM on 512MB instance
                del quote, df
                gc.collect()

        return results

    @app.get("/listing/symbols")
    def listing_symbols(
        source: str = "VCI",
        x_api_key: str = Header(None),
    ):
        """Get all available symbols."""
        verify_api_key(x_api_key)
        from vnstock_data import Listing

        try:
            listing = Listing(source=source)
            df = listing.all_symbols()
            return {"data": df.to_dict(orient="records"), "count": len(df)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get("/listing/indices")
    def listing_indices(
        source: str = "VCI",
        x_api_key: str = Header(None),
    ):
        """Get all available indices."""
        verify_api_key(x_api_key)
        from vnstock_data import Listing

        try:
            listing = Listing(source=source)
            df = listing.all_indices()
            return {"data": df.to_dict(orient="records"), "count": len(df)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
