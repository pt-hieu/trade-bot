"""Trading route handlers — /trading/* and /ticker/enrichment endpoints."""

import gc
import math
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Query


def register_trading_routes(app, verify_api_key):
    @app.get("/trading/foreign")
    def trading_foreign(
        symbols: str = Query(..., description="Comma-separated symbols"),
        start: str = None,
        end: str = None,
        x_api_key: str = Header(None),
    ):
        """Fetch foreign investor flow per symbol."""
        verify_api_key(x_api_key)
        from vnstock_data import Trading

        if not start:
            start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")

        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        results = {}

        for symbol in symbol_list:
            try:
                tr = Trading(symbol=symbol, source="CafeF")
                df = tr.foreign_trade(start=start, end=end)
                # Include date index in records
                if df.index.name or hasattr(df.index, "date"):
                    df = df.reset_index()
                data = df.to_dict(orient="records")

                for row in data:
                    for k, v in row.items():
                        if hasattr(v, "isoformat"):
                            row[k] = v.isoformat()

                results[symbol] = {"data": data, "count": len(data)}
            except Exception as e:
                results[symbol] = {"error": str(e)}
            finally:
                gc.collect()

        return results

    @app.get("/trading/prop")
    def trading_prop(
        symbols: str = Query(..., description="Comma-separated symbols"),
        start: str = None,
        end: str = None,
        x_api_key: str = Header(None),
    ):
        """Fetch proprietary trading desk flow per symbol."""
        verify_api_key(x_api_key)
        from vnstock_data import Trading

        if not start:
            start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")

        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        results = {}

        for symbol in symbol_list:
            try:
                tr = Trading(symbol=symbol, source="CafeF")
                df = tr.prop_trade(start=start, end=end)
                if df.index.name or hasattr(df.index, "date"):
                    df = df.reset_index()
                data = df.to_dict(orient="records")
                for row in data:
                    for k, v in row.items():
                        if hasattr(v, "isoformat"):
                            row[k] = v.isoformat()
                results[symbol] = {"data": data, "count": len(data)}
            except Exception as e:
                results[symbol] = {"error": str(e)}
            finally:
                gc.collect()

        return results

    @app.get("/trading/orders")
    def trading_orders(
        symbols: str = Query(..., description="Comma-separated symbols"),
        start: str = None,
        end: str = None,
        x_api_key: str = Header(None),
    ):
        """Fetch order statistics (buy/sell order counts and sizes) per symbol."""
        verify_api_key(x_api_key)
        from vnstock_data import Trading

        if not start:
            start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")

        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        results = {}

        for symbol in symbol_list:
            try:
                tr = Trading(symbol=symbol, source="CafeF")
                df = tr.order_stats(start=start, end=end)
                if df.index.name or hasattr(df.index, "date"):
                    df = df.reset_index()
                data = df.to_dict(orient="records")
                for row in data:
                    for k, v in row.items():
                        if hasattr(v, "isoformat"):
                            row[k] = v.isoformat()
                results[symbol] = {"data": data, "count": len(data)}
            except Exception as e:
                results[symbol] = {"error": str(e)}
            finally:
                gc.collect()

        return results

    @app.get("/trading/foreign-top")
    def trading_foreign_top(
        limit: int = Query(10, le=20),
        date: str = None,
        x_api_key: str = Header(None),
    ):
        """Fetch top foreign bought/sold stocks."""
        verify_api_key(x_api_key)
        from vnstock_data import TopStock

        try:
            insights = TopStock()
            bought = insights.foreign_buy(date=date, limit=limit)
            sold = insights.foreign_sell(date=date, limit=limit)

            return {
                "top_bought": bought.to_dict(orient="records") if bought is not None else [],
                "top_sold": sold.to_dict(orient="records") if sold is not None else [],
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get("/ticker/enrichment")
    def ticker_enrichment(
        symbols: str = Query(..., description="Comma-separated symbols"),
        modules: str = Query(
            "flow,prop,orders", description="Comma-separated: flow,prop,orders,insider,events"
        ),
        days: int = Query(5, le=30, description="Lookback days for flow/prop/orders"),
        x_api_key: str = Header(None),
    ):
        """Composite enrichment endpoint: fetch multiple data modules per ticker in one call.

        Modules:
        - flow: Foreign investor flow (buy/sell/net/room)
        - prop: Proprietary trading desk flow
        - orders: Order statistics (buy/sell counts and sizes)
        - insider: Recent insider transactions
        - events: Upcoming corporate events (dividends, AGMs)

        Returns: { "FPT": { "flow": {...}, "prop": {...} }, ... }
        """
        verify_api_key(x_api_key)
        from vnstock_data import Company, Trading

        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        module_list = [m.strip() for m in modules.split(",") if m.strip()]
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")

        def _to_records(df):
            """Convert DataFrame to JSON-safe records."""
            if df is None or df.empty:
                return []
            if df.index.name or hasattr(df.index, "date"):
                df = df.reset_index()
            data = df.to_dict(orient="records")
            for row in data:
                for k, v in row.items():
                    if hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
                    elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        row[k] = None
            return data

        results = {}
        # Process symbols in groups of 5 for nano-friendliness
        chunk_size = 5
        chunks = [symbol_list[i : i + chunk_size] for i in range(0, len(symbol_list), chunk_size)]

        for chunk in chunks:
            for symbol in chunk:
                sym_result = {}

                if "flow" in module_list:
                    try:
                        tr = Trading(symbol=symbol, source="CafeF")
                        df = tr.foreign_trade(start=start, end=end)
                        sym_result["flow"] = _to_records(df)
                    except Exception as e:
                        sym_result["flow"] = {"error": str(e)}
                    finally:
                        gc.collect()

                if "prop" in module_list:
                    try:
                        tr = Trading(symbol=symbol, source="CafeF")
                        df = tr.prop_trade(start=start, end=end)
                        sym_result["prop"] = _to_records(df)
                    except Exception as e:
                        sym_result["prop"] = {"error": str(e)}
                    finally:
                        gc.collect()

                if "orders" in module_list:
                    try:
                        tr = Trading(symbol=symbol, source="CafeF")
                        df = tr.order_stats(start=start, end=end)
                        sym_result["orders"] = _to_records(df)
                    except Exception as e:
                        sym_result["orders"] = {"error": str(e)}
                    finally:
                        gc.collect()

                if "insider" in module_list:
                    try:
                        tr = Trading(symbol=symbol, source="VCI")
                        df = tr.insider_deal(limit=10)
                        sym_result["insider"] = _to_records(df)
                    except Exception as e:
                        sym_result["insider"] = {"error": str(e)}
                    finally:
                        gc.collect()

                if "events" in module_list:
                    try:
                        co = Company(symbol=symbol, source="VCI")
                        df = co.events()
                        sym_result["events"] = _to_records(df)
                    except Exception as e:
                        sym_result["events"] = {"error": str(e)}
                    finally:
                        gc.collect()

                results[symbol] = sym_result

        return results
