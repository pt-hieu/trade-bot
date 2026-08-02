"""Market route handlers — /market/*, /commodities/* endpoints."""

import gc
import math
from datetime import datetime

from fastapi import Header, HTTPException, Query

# ── In-memory caches ────────────────────────────────────────────────────
_commodity_cache: dict = {"data": None, "fetched_at": None}
_COMMODITY_CACHE_TTL_HOURS = 6

_valuation_cache: dict = {"data": None, "fetched_at": None}
_VALUATION_CACHE_TTL_HOURS = 24

COMMODITY_METHODS = {
    "gold_global": "gold_global",
    "steel_hrc": "steel_hrc",
    "iron_ore": "iron_ore",
    "oil_crude": "oil_crude",
    "gas_vn": "gas_vn",
    "fertilizer_ure": "fertilizer_ure",
}

DEFAULT_COMMODITIES = list(COMMODITY_METHODS.keys())


def _safe_float(value) -> float | None:
    """Convert to float, returning None for NaN/Inf."""
    if value is None:
        return None
    try:
        float_value = float(value)
        if math.isnan(float_value) or math.isinf(float_value):
            return None
        return float_value
    except (ValueError, TypeError):
        return None


def _compute_change_pct(latest: float, historical: float | None) -> float | None:
    """Compute % change between two prices."""
    if historical is None or historical == 0:
        return None
    return round((latest - historical) / historical * 100, 2)


def register_market_routes(app, verify_api_key):
    @app.get("/market/deals")
    def market_deals(
        limit: int = Query(20, le=50),
        x_api_key: str = Header(None),
    ):
        """Fetch top tickers by block trade / deal volume (VNINDEX)."""
        verify_api_key(x_api_key)
        from vnstock_data import TopStock

        try:
            insights = TopStock()
            df = insights.deal(index="VNINDEX", limit=limit)
            if df is None or df.empty:
                return {"data": [], "count": 0}
            data = df.to_dict(orient="records")
            for row in data:
                for k, v in row.items():
                    if hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
            return {"data": data, "count": len(data)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get("/market/breadth")
    def market_breadth(x_api_key: str = Header(None)):
        """Compute market advance/decline breadth ratio from VNINDEX gainers/losers."""
        verify_api_key(x_api_key)
        from vnstock_data import TopStock

        try:
            insights = TopStock()
            gainers = insights.gainer(index="VNINDEX", limit=1000)
            losers = insights.loser(index="VNINDEX", limit=1000)
            advance_count = len(gainers) if gainers is not None else 0
            decline_count = len(losers) if losers is not None else 0
            breadth_ratio = round(advance_count / max(decline_count, 1), 2)
            return {
                "advance": advance_count,
                "decline": decline_count,
                "breadth_ratio": breadth_ratio,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get("/commodities/prices")
    def commodities_prices(
        commodities: str = Query(",".join(DEFAULT_COMMODITIES)),
        x_api_key: str = Header(None),
    ):
        """Fetch commodity prices with 5d/20d change % from vnstock_data.CommodityPrice."""
        verify_api_key(x_api_key)

        now = datetime.now()
        if (
            _commodity_cache["data"]
            and _commodity_cache["fetched_at"]
            and (now - _commodity_cache["fetched_at"]).total_seconds()
            < _COMMODITY_CACHE_TTL_HOURS * 3600
        ):
            return _commodity_cache["data"]

        from vnstock_data import CommodityPrice

        requested = [commodity.strip() for commodity in commodities.split(",") if commodity.strip()]
        commodity_source = CommodityPrice()
        results = {}

        for commodity_key in requested:
            method_name = COMMODITY_METHODS.get(commodity_key)
            if not method_name:
                continue
            try:
                method = getattr(commodity_source, method_name)
                dataframe = method()
                if dataframe is None or dataframe.empty:
                    continue

                if commodity_key == "gas_vn":
                    # gas_vn returns ron95/ron92/oil_do columns instead of OHLCV
                    latest_row = dataframe.iloc[-1]
                    latest_price = _safe_float(latest_row.get("ron95"))
                    row_5d = dataframe.iloc[-6] if len(dataframe) >= 6 else None
                    row_20d = dataframe.iloc[-21] if len(dataframe) >= 21 else None
                    price_5d = _safe_float(row_5d.get("ron95")) if row_5d is not None else None
                    price_20d = _safe_float(row_20d.get("ron95")) if row_20d is not None else None
                    results[commodity_key] = {
                        "price": latest_price,
                        "ron92": _safe_float(latest_row.get("ron92")),
                        "oil_do": _safe_float(latest_row.get("oil_do")),
                        "change_5d_pct": _compute_change_pct(latest_price, price_5d)
                        if latest_price
                        else None,
                        "change_20d_pct": _compute_change_pct(latest_price, price_20d)
                        if latest_price
                        else None,
                        "unit": "VND/L",
                        "last_date": str(dataframe.index[-1].date())
                        if hasattr(dataframe.index[-1], "date")
                        else str(dataframe.index[-1]),
                    }
                else:
                    latest_close = _safe_float(dataframe.iloc[-1].get("close"))
                    close_1d = (
                        _safe_float(dataframe.iloc[-2].get("close"))
                        if len(dataframe) >= 2
                        else None
                    )
                    close_5d = (
                        _safe_float(dataframe.iloc[-6].get("close"))
                        if len(dataframe) >= 6
                        else None
                    )
                    close_20d = (
                        _safe_float(dataframe.iloc[-21].get("close"))
                        if len(dataframe) >= 21
                        else None
                    )
                    unit_map = {
                        "gold_global": "USD/oz",
                        "steel_hrc": "USD/t",
                        "iron_ore": "USD/t",
                        "oil_crude": "USD/bbl",
                        "fertilizer_ure": "USD/t",
                    }
                    results[commodity_key] = {
                        "price": latest_close,
                        "change_1d_pct": _compute_change_pct(latest_close, close_1d)
                        if latest_close
                        else None,
                        "change_5d_pct": _compute_change_pct(latest_close, close_5d)
                        if latest_close
                        else None,
                        "change_20d_pct": _compute_change_pct(latest_close, close_20d)
                        if latest_close
                        else None,
                        "unit": unit_map.get(commodity_key, ""),
                        "last_date": str(dataframe.index[-1].date())
                        if hasattr(dataframe.index[-1], "date")
                        else str(dataframe.index[-1]),
                    }
                del dataframe
            except Exception as commodity_error:
                import logging as _logging

                _logging.getLogger("routes_market").warning(
                    "Commodity %s fetch failed: %s", commodity_key, commodity_error
                )
                results[commodity_key] = {"error": str(commodity_error)}

        gc.collect()
        response = {
            "commodities": results,
            "count": len(results),
            "timestamp": now.isoformat(),
        }
        _commodity_cache["data"] = response
        _commodity_cache["fetched_at"] = now
        return response

    @app.get("/market/valuation")
    def market_valuation(x_api_key: str = Header(None)):
        """Fetch VN-Index PE/PB with 5Y percentile — computed server-side."""
        verify_api_key(x_api_key)

        now = datetime.now()
        if (
            _valuation_cache["data"]
            and _valuation_cache["fetched_at"]
            and (now - _valuation_cache["fetched_at"]).total_seconds()
            < _VALUATION_CACHE_TTL_HOURS * 3600
        ):
            return _valuation_cache["data"]

        from vnstock_data import Market

        try:
            market = Market()
            dataframe = market.evaluation(duration="5Y")
            if dataframe is None or dataframe.empty:
                raise HTTPException(status_code=404, detail="No valuation data available")

            pe_series = dataframe["pe"].dropna().tolist()
            pb_series = dataframe["pb"].dropna().tolist()

            latest_pe = _safe_float(pe_series[-1]) if pe_series else None
            latest_pb = _safe_float(pb_series[-1]) if pb_series else None

            pe_percentile = None
            pb_percentile = None
            if latest_pe is not None and len(pe_series) > 1:
                below_count = sum(1 for value in pe_series if value < latest_pe)
                pe_percentile = round(below_count / len(pe_series) * 100)
            if latest_pb is not None and len(pb_series) > 1:
                below_count = sum(1 for value in pb_series if value < latest_pb)
                pb_percentile = round(below_count / len(pb_series) * 100)

            del dataframe
            gc.collect()

            response = {
                "pe": latest_pe,
                "pe_percentile": pe_percentile,
                "pb": latest_pb,
                "pb_percentile": pb_percentile,
                "data_points": len(pe_series),
                "timestamp": now.isoformat(),
            }
            _valuation_cache["data"] = response
            _valuation_cache["fetched_at"] = now
            return response
        except HTTPException:
            raise
        except Exception as valuation_error:
            raise HTTPException(status_code=500, detail=str(valuation_error)) from valuation_error
