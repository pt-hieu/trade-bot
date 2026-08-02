"""Macro route handlers — /macro/* endpoints."""

import gc
import math
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException

# ── In-memory cache for SBV exchange rate ─────────────────────────────
# SBV central rate updates once per business day; 6h TTL avoids repeated
# scrape failures while staying fresh enough for daily pipeline runs.
_exr_cache: dict = {"data": None, "fetched_at": None}
_EXR_CACHE_TTL_HOURS = 6


def _safe_float(value) -> float | None:
    """Convert to float, returning None for NaN/Inf."""
    if value is None:
        return None
    try:
        float_value = float(value)
        if math.isnan(float_value) or math.isinf(float_value):
            return None
        return float_value
    except (TypeError, ValueError):
        return None


from vn_snapshot import fetch_vn_snapshot


def register_macro_routes(app, verify_api_key):
    @app.get("/macro/global")
    def macro_global(x_api_key: str = Header(None)):
        """Fetch DXY, VIX, USD/VND, copper, oil, US 10Y yield, Shanghai, and US indices via yfinance."""
        verify_api_key(x_api_key)
        import yfinance as yf

        result = {"timestamp": datetime.now().isoformat()}

        tickers = [
            ("DX-Y.NYB", "dxy"),
            ("^VIX", "vix"),
            ("USDVND=X", "usd_vnd"),
            ("HG=F", "copper"),
            ("CL=F", "oil"),
            ("^TNX", "us_10y"),
            ("000001.SS", "shanghai"),
            ("^GSPC", "sp500"),
            ("^IXIC", "nasdaq"),
            ("^DJI", "dow"),
        ]
        from datetime import timezone  # noqa: F401 — kept for future use

        for ticker, key in tickers:
            try:
                data = yf.Ticker(ticker)
                hist = data.history(period="5d")
                if len(hist) >= 2:
                    current = _safe_float(hist["Close"].iloc[-1])
                    previous = _safe_float(hist["Close"].iloc[-2])
                    if current is None or previous is None or previous == 0:
                        result[key] = {"error": "NaN/missing value from yfinance"}
                        continue
                    change_pct = round((current - previous) / previous * 100, 2)
                    # Staleness check: last data point should be within 4 calendar days
                    last_date = hist.index[-1]
                    if hasattr(last_date, "tz_localize"):
                        last_date = last_date.to_pydatetime()
                    now_utc = datetime.now(UTC)
                    last_utc = last_date if last_date.tzinfo else last_date.replace(tzinfo=UTC)
                    days_old = (now_utc - last_utc).days
                    entry = {"value": round(current, 4), "change_pct": change_pct}
                    if days_old > 4:
                        entry["possibly_stale"] = True
                        entry["last_date"] = str(hist.index[-1].date())
                    result[key] = entry
                elif len(hist) == 1:
                    single_value = _safe_float(hist["Close"].iloc[-1])
                    if single_value is None:
                        result[key] = {"error": "NaN value from yfinance"}
                        continue
                    result[key] = {
                        "value": round(single_value, 4),
                        "change_pct": 0.0,
                    }
                else:
                    result[key] = {"error": "No data"}
            except Exception as e:
                result[key] = {"error": str(e)}
            finally:
                gc.collect()

        return result

    @app.get("/macro/exchange-rate")
    def exchange_rate(
        start: str = None,
        end: str = None,
        x_api_key: str = Header(None),
    ):
        """Fetch USD/VND exchange rate via vnstock_data (6h cached for default params)."""
        verify_api_key(x_api_key)

        now = datetime.now()
        use_cache = start is None and end is None
        if (
            use_cache
            and _exr_cache["data"]
            and _exr_cache["fetched_at"]
            and (now - _exr_cache["fetched_at"]).total_seconds() < _EXR_CACHE_TTL_HOURS * 3600
        ):
            return _exr_cache["data"]

        from vnstock_data import Macro

        if not start:
            start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end:
            end = now.strftime("%Y-%m-%d")

        try:
            import math

            macro = Macro()
            df = macro.exchange_rate(start=start, end=end, period="day")
            df = df.fillna(0)  # Replace NaN with 0 for JSON serialization
            data = df.to_dict(orient="records")

            for row in data:
                for k, v in row.items():
                    if hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
                    elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        row[k] = 0.0

            latest = data[-1] if data else {}
            result = {"latest": latest, "data": data, "count": len(data)}

            if use_cache:
                _exr_cache["data"] = result
                _exr_cache["fetched_at"] = now
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get("/macro/vn-snapshot")
    def vn_snapshot(x_api_key: str = Header(None)):
        """VN economy snapshot: CPI, credit, GDP, FDI from vnstock_data.Macro()."""
        verify_api_key(x_api_key)
        return fetch_vn_snapshot()
