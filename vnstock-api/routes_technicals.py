"""Technical indicator route handlers — /technicals/* endpoints."""

import math
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Query


def _tail_series(series, n=5):
    """Return the last n NaN-stripped float values from a pandas Series (newest last).

    Returns None if fewer than 2 clean values remain — consumers need ≥2 to
    derive direction. Used for ADX/RSI/MACD-histogram direction derivation.
    """
    if series is None or series.empty:
        return None
    tail = series.tail(n).tolist()
    # NaN-strip — pandas-ta emits leading NaN during indicator warmup.
    clean = [float(v) for v in tail if v == v]
    return clean if len(clean) >= 2 else None


def _compute_latest_indicators(ind, df):
    """Extract all indicator values from the last bar of a fitted Indicator."""
    rsi = ind.rsi(14)
    rsi_val = float(rsi.iloc[-1]) if rsi is not None and not rsi.empty else None
    rsi_series_val = _tail_series(rsi, n=5)

    macd_df = ind.macd(12, 26, 9)
    macd_val = None
    if macd_df is not None and not macd_df.empty:
        macd_val = {
            "MACD": float(macd_df["MACD_12_26_9"].iloc[-1]),
            "signal": float(macd_df["MACDs_12_26_9"].iloc[-1]),
            "histogram": float(macd_df["MACDh_12_26_9"].iloc[-1]),
            "histogram_series": _tail_series(macd_df["MACDh_12_26_9"], n=5),
        }

    sma20 = ind.sma(20)
    sma50 = ind.sma(50)
    sma20_val = (
        float(sma20.iloc[-1]) if sma20 is not None and not sma20.empty and len(df) >= 20 else None
    )
    sma50_val = (
        float(sma50.iloc[-1]) if sma50 is not None and not sma50.empty and len(df) >= 50 else None
    )

    atr = ind.atr(14)
    atr_val = float(atr.iloc[-1]) if atr is not None and not atr.empty else None

    supertrend_df = ind.supertrend(10, 3)
    supertrend_val = None
    if supertrend_df is not None and not supertrend_df.empty:
        row = supertrend_df.iloc[-1]
        direction = int(row["SUPERTd_10_3.0"])
        supertrend_val = {
            "value": float(row["SUPERT_10_3.0"]),
            "direction": "UP" if direction == 1 else "DOWN",
            # NaN-safe: NaN != NaN is True in Python
            "lower": float(row["SUPERTl_10_3.0"])
            if row["SUPERTl_10_3.0"] == row["SUPERTl_10_3.0"]
            else None,
            "upper": float(row["SUPERTs_10_3.0"])
            if row["SUPERTs_10_3.0"] == row["SUPERTs_10_3.0"]
            else None,
        }

    adx_df = ind.adx(14)
    adx_val = None
    if adx_df is not None and not adx_df.empty:
        row = adx_df.iloc[-1]
        adx_val = {
            "adx": float(row["ADX_14"]),
            "dmp": float(row["DMP_14"]),
            "dmn": float(row["DMN_14"]),
            "series": _tail_series(adx_df["ADX_14"], n=5),
        }

    bbands_df = ind.bbands(14, 2)
    bbands_val = None
    if bbands_df is not None and not bbands_df.empty:
        row = bbands_df.iloc[-1]
        bbands_val = {
            "lower": float(row["BBL_14_2.0"]),
            "middle": float(row["BBM_14_2.0"]),
            "upper": float(row["BBU_14_2.0"]),
            "bandwidth": float(row["BBB_14_2.0"]),
            "percent": float(row["BBP_14_2.0"]),
        }

    stoch_df = ind.stoch(14, 3, 3)
    stoch_val = None
    if stoch_df is not None and not stoch_df.empty:
        row = stoch_df.iloc[-1]
        stoch_val = {"k": float(row["STOCHk_14_3_3"]), "d": float(row["STOCHd_14_3_3"])}

    return {
        "date": str(df.index[-1])[:10],
        "close": float(df["close"].iloc[-1]),
        "rsi": rsi_val,
        "rsi_series": rsi_series_val,
        "macd": macd_val,
        "sma20": sma20_val,
        "sma50": sma50_val,
        "atr": atr_val,
        "supertrend": supertrend_val,
        "adx": adx_val,
        "bbands": bbands_val,
        "stoch": stoch_val,
    }


def _safe_float(series, idx):
    if series is None or series.empty or idx >= len(series):
        return None
    v = series.iloc[idx]
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), 4)


def register_technicals_routes(app, verify_api_key):
    @app.get("/technicals")
    def get_technicals(
        symbol: str,
        source: str = "VCI",
        start: str = None,
        end: str = None,
        x_api_key: str = Header(None),
    ):
        """Calculate technical indicators for a symbol using vnstock_ta."""
        verify_api_key(x_api_key)
        from vnstock_data import Quote
        from vnstock_ta import Indicator

        if not start:
            start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")

        try:
            quote = Quote(source=source, symbol=symbol)
            df = quote.history(start=start, end=end, interval="1D")
            df = df.set_index("time")

            if len(df) < 26:  # Need enough data for MACD
                raise HTTPException(status_code=400, detail="Insufficient data")

            ind = Indicator(data=df)
            return {"symbol": symbol, **_compute_latest_indicators(ind, df)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get("/technicals/history")
    def get_technicals_history(
        symbol: str,
        source: str = "VCI",
        start: str = None,
        end: str = None,
        x_api_key: str = Header(None),
    ):
        """Return technical indicator time series for all dates in range.

        Unlike /technicals which returns only the latest bar, this endpoint
        returns RSI, MACD, SMA20, SMA50 for every date in the range.
        Used for ML training data backfill.
        """
        verify_api_key(x_api_key)
        from vnstock_data import Quote
        from vnstock_ta import Indicator

        if not start:
            start = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")

        try:
            quote = Quote(source=source, symbol=symbol)
            df = quote.history(start=start, end=end, interval="1D")
            df = df.set_index("time")

            if len(df) < 26:
                raise HTTPException(status_code=400, detail="Insufficient data")

            ind = Indicator(data=df)
            rsi_series = ind.rsi(14)
            macd_df = ind.macd(12, 26, 9)
            sma20_series = ind.sma(20)
            sma50_series = ind.sma(50)

            data = []
            for i in range(len(df)):
                macd_val = None
                if macd_df is not None and not macd_df.empty and i < len(macd_df):
                    macd_df.iloc[i]
                    m = _safe_float(macd_df["MACD_12_26_9"], i)
                    s = _safe_float(macd_df["MACDs_12_26_9"], i)
                    h = _safe_float(macd_df["MACDh_12_26_9"], i)
                    if m is not None:
                        macd_val = {"MACD": m, "signal": s, "histogram": h}

                data.append(
                    {
                        "date": str(df.index[i])[:10],
                        "close": round(float(df["close"].iloc[i]), 2),
                        "rsi": _safe_float(rsi_series, i),
                        "macd": macd_val,
                        "sma20": _safe_float(sma20_series, i),
                        "sma50": _safe_float(sma50_series, i),
                    }
                )

            return {"symbol": symbol, "count": len(data), "data": data}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get("/technicals/batch")
    def get_technicals_batch(
        symbols: str = Query(..., description="Comma-separated symbols"),
        source: str = "VCI",
        start: str = None,
        end: str = None,
        x_api_key: str = Header(None),
    ):
        """Calculate technical indicators for multiple symbols."""
        verify_api_key(x_api_key)
        from vnstock_data import Quote
        from vnstock_ta import Indicator

        if not start:
            start = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")

        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        results = {}

        for symbol in symbol_list:
            try:
                quote = Quote(source=source, symbol=symbol)
                df = quote.history(start=start, end=end, interval="1D")
                df = df.set_index("time")

                if len(df) < 26:
                    results[symbol] = {"error": "Insufficient data"}
                    continue

                ind = Indicator(data=df)
                results[symbol] = _compute_latest_indicators(ind, df)
            except Exception as e:
                results[symbol] = {"error": str(e)}

        return results
