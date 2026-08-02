"""Financials route handlers — /financials/statements and /financials/ratios."""

import gc
import math

from fastapi import Header, HTTPException, Query


def register_financials_routes(app, verify_api_key):
    @app.get("/financials/statements")
    def financials_statements(
        symbol: str,
        statement_type: str = Query("income", description="income|balance_sheet|cash_flow"),
        period: str = Query("quarter", description="quarter|year"),
        source: str = "VCI",
        limit: int = Query(8, le=20),
        x_api_key: str = Header(None),
    ):
        """Fetch financial statements for a symbol."""
        verify_api_key(x_api_key)
        from vnstock_data import Finance

        finance = None
        df = None
        try:
            finance = Finance(source=source, symbol=symbol.upper())

            if statement_type == "income":
                df = finance.income_statement(period=period)
            elif statement_type == "balance_sheet":
                df = finance.balance_sheet(period=period)
            elif statement_type == "cash_flow":
                df = finance.cash_flow(period=period)
            else:
                raise HTTPException(
                    status_code=400, detail=f"Invalid statement_type: {statement_type}"
                )

            if df is None or df.empty:
                return {
                    "symbol": symbol.upper(),
                    "statement_type": statement_type,
                    "period": period,
                    "data": [],
                    "count": 0,
                }

            # Index has period values like '2025-Q3'; reset to include in records
            df = df.tail(limit).reset_index().fillna(0)
            data = df.to_dict(orient="records")
            for row in data:
                for k, v in row.items():
                    if hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
                    elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        row[k] = 0.0

            # Reverse so latest period is first
            data.reverse()
            return {
                "symbol": symbol.upper(),
                "statement_type": statement_type,
                "period": period,
                "data": data,
                "count": len(data),
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        finally:
            del finance, df
            gc.collect()

    @app.get("/financials/ratios")
    def financials_ratios(
        symbol: str,
        period: str = Query("quarter", description="quarter|year"),
        source: str = "VCI",
        limit: int = Query(8, le=20),
        x_api_key: str = Header(None),
    ):
        """Fetch financial ratios for a symbol."""
        verify_api_key(x_api_key)
        from vnstock_data import Finance

        finance = None
        df = None
        try:
            finance = Finance(source=source, symbol=symbol.upper())
            df = finance.ratio(period=period)

            if df is None or df.empty:
                return {"symbol": symbol.upper(), "period": period, "data": [], "count": 0}

            df = df.tail(limit).reset_index().fillna(0)
            data = df.to_dict(orient="records")
            for row in data:
                for k, v in row.items():
                    if hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
                    elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        row[k] = 0.0

            data.reverse()
            return {"symbol": symbol.upper(), "period": period, "data": data, "count": len(data)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        finally:
            del finance, df
            gc.collect()
