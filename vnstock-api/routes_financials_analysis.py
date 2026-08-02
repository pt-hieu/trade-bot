"""Advanced financial analysis routes — /financials/valuation-history and /financials/earnings-quality."""

import gc

from fastapi import Header, HTTPException, Query
from financials_helpers import (
    BANK_TICKERS,
    cagr,
    clean_rows,
    core_ratio,
    decompose_earnings,
    earnings_quality_grade,
    get_first_valid,
    ratio_trend,
    stat_block,
    to_pct,
    trend_direction,
)


def register_financials_analysis_routes(app, verify_api_key):
    @app.get("/financials/valuation-history")
    def financials_valuation_history(
        symbol: str,
        periods: int = Query(8, le=20),
        x_api_key: str = Header(None),
    ):
        """8-quarter valuation percentiles and EPS/margin trajectory."""
        verify_api_key(x_api_key)
        from vnstock_data import Finance

        finance = None
        df = None
        try:
            finance = Finance(source="VCI", symbol=symbol.upper())
            df = finance.ratio(period="quarter")

            if df is None or df.empty:
                return {"symbol": symbol.upper(), "error": "no data"}

            rows = clean_rows(df.tail(periods).reset_index().fillna(0))

            pe_vals = [
                v
                for v in (get_first_valid(r, "P/E", "pe") for r in rows)
                if v is not None and v > 0
            ]
            pb_vals = [
                v
                for v in (get_first_valid(r, "P/B", "pb") for r in rows)
                if v is not None and v > 0
            ]
            roe_vals = [
                v
                for v in (to_pct(get_first_valid(r, "ROE (%)", "roe")) for r in rows)
                if v is not None
            ]
            nm_vals = [
                v
                for v in (
                    to_pct(get_first_valid(r, "After-tax Profit Margin (%)", "net_margin"))
                    for r in rows
                )
                if v is not None
            ]
            eps_vals = [
                v
                for v in (get_first_valid(r, "EPS basic (VND)", "eps") for r in rows)
                if v is not None
            ]
            period_labels = [str(r.get("period") or r.get("yearReport") or "?") for r in rows]

            result: dict = {
                "symbol": symbol.upper(),
                "periods": len(rows),
                "latest_period": period_labels[0] if period_labels else None,
            }

            if len(pe_vals) >= 2:
                result["pe"] = stat_block(pe_vals[1:], pe_vals[0])
            if len(pb_vals) >= 2:
                result["pb"] = stat_block(pb_vals[1:], pb_vals[0])
            if len(roe_vals) >= 2:
                result["roe"] = stat_block(roe_vals[1:], roe_vals[0])
            if len(nm_vals) >= 2:
                result["net_margin"] = stat_block(nm_vals[1:], nm_vals[0])

            if eps_vals:
                eps_cagr = cagr(eps_vals)
                result["eps_trajectory"] = {
                    "latest": round(eps_vals[0]),
                    "trend": trend_direction([float(v) for v in eps_vals]),
                    "cagr_4q": round(eps_cagr, 3) if eps_cagr is not None else None,
                }

            if nm_vals:
                avg = sum(nm_vals) / len(nm_vals)
                result["margin_trajectory"] = {
                    "trend": trend_direction(nm_vals),
                    "latest": round(nm_vals[0], 1),
                    "avg": round(avg, 1),
                    "vs_avg": round(nm_vals[0] - avg, 1),
                }

            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        finally:
            del finance, df
            gc.collect()

    @app.get("/financials/earnings-quality")
    def financials_earnings_quality(
        symbol: str,
        periods: int = Query(4, le=8),
        x_api_key: str = Header(None),
    ):
        """Decompose earnings into core vs non-core income over N quarters."""
        verify_api_key(x_api_key)
        from vnstock_data import Finance

        finance = None
        df = None
        try:
            sym = symbol.upper()
            is_bank = sym in BANK_TICKERS

            finance = Finance(source="VCI", symbol=sym)
            df = finance.income_statement(period="quarter")

            if df is None or df.empty:
                return {"symbol": sym, "error": "no income statement data"}

            rows = clean_rows(df.tail(periods).reset_index().fillna(0))

            quarterly = []
            core_ratios = []

            for row in rows:
                period_val = str(row.get("period") or row.get("yearReport") or "?")
                decomp = decompose_earnings(row, is_bank)
                ratio = core_ratio(decomp["core_profit"], decomp["net_income"])
                entry = {
                    "period": period_val,
                    "revenue": decomp["revenue"],
                    "core_profit": decomp["core_profit"],
                    "non_core": decomp["non_core"],
                    "net_income": decomp["net_income"],
                    "core_ratio": round(ratio, 3) if ratio is not None else None,
                }
                quarterly.append(entry)
                if ratio is not None:
                    core_ratios.append(ratio)

            latest = quarterly[0] if quarterly else {}
            latest_ratio = latest.get("core_ratio")

            return {
                "symbol": sym,
                "is_bank": is_bank,
                "periods": len(quarterly),
                "latest": latest,
                "core_ratios": core_ratios,
                "core_ratio_trend": ratio_trend(core_ratios) if core_ratios else "STABLE",
                "quality_grade": earnings_quality_grade(latest_ratio)
                if latest_ratio is not None
                else "UNKNOWN",
                "quarterly": quarterly,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        finally:
            del finance, df
            gc.collect()
