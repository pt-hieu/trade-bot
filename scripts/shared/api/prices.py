"""Price data and derived metrics — reads directly from vnstock API.

Returns prices in VND integers (rule 18). vnstock API returns prices in
thousands VND — conversion happens here at the normalization boundary.

Replaces:
- mv_relative_strength materialized view → compute_relative_strength()
- v_daily_returns SQL view → compute_daily_return()
- daily_prices table reads in pipeline consumers → get_prices()
"""

from datetime import datetime, timedelta

from ..config import VIETNAM_TZ
from ..units import thousands_to_vnd
from ..vnstock_client import fetch_history_batch


def _start_date(days: int) -> str:
    """Start date string with buffer for weekends/holidays."""
    return (datetime.now(VIETNAM_TZ) - timedelta(days=days + 10)).strftime("%Y-%m-%d")


def _today() -> str:
    return datetime.now(VIETNAM_TZ).strftime("%Y-%m-%d")


def _extract_closes(data: dict) -> list[float]:
    """Extract sorted close prices from a fetch_history_batch symbol result."""
    records = data.get("data", []) if isinstance(data, dict) else []
    closes = []
    for r in records:
        try:
            closes.append(float(r["close"]))
        except (KeyError, TypeError, ValueError):
            continue
    return closes


# ── Public functions ──────────────────────────────────────────────────────────


async def get_prices(tickers: list[str], days: int = 10) -> dict[str, dict]:
    """Get latest OHLCV bar for each ticker.

    Returns {ticker: {date, open, high, low, close, volume}} dict.
    Prices in VND integers (converted from vnstock thousands).
    Replaces direct reads from daily_prices table for current-day data.
    """
    if not tickers:
        return {}

    result = await fetch_history_batch(
        symbols=[t.upper() for t in tickers],
        start=_start_date(days),
        end=_today(),
    )

    prices = {}
    for ticker, data in result.items():
        if not isinstance(data, dict) or "error" in data:
            continue
        records = data.get("data", [])
        if not records:
            continue
        latest = records[-1]
        try:
            prev_close = float(records[-2]["close"]) if len(records) >= 2 else None
            curr_close = float(latest["close"])
            change_pct = (
                round((curr_close - prev_close) / prev_close * 100, 2)
                if prev_close and prev_close > 0
                else None
            )
            prices[ticker] = {
                "date": str(latest.get("time", ""))[:10],
                "open": thousands_to_vnd(latest.get("open")),
                "high": thousands_to_vnd(latest.get("high")),
                "low": thousands_to_vnd(latest.get("low")),
                "close": thousands_to_vnd(curr_close),
                "volume": latest.get("volume"),
                "change_pct": change_pct,
            }
        except (KeyError, TypeError, ValueError):
            continue

    return prices


async def get_ohlc_series(
    tickers: list[str],
    start: str,
    end: str,
) -> dict[str, list[dict]]:
    """Get multi-day OHLCV series for each ticker.

    Returns {ticker: [{date, open, high, low, close}, ...]} sorted chronologically.
    Prices in VND integers. Used for multi-day evaluations (e.g., PENDING resolution).
    """
    if not tickers:
        return {}

    result = await fetch_history_batch(
        symbols=[t.upper() for t in tickers],
        start=start,
        end=end,
    )

    series: dict[str, list[dict]] = {}
    for ticker, data in result.items():
        if not isinstance(data, dict) or "error" in data:
            continue
        records = data.get("data") or []
        bars = []
        for record in records:
            try:
                bars.append(
                    {
                        "date": str(record.get("time", ""))[:10],
                        "open": thousands_to_vnd(record.get("open")),
                        "high": thousands_to_vnd(record.get("high")),
                        "low": thousands_to_vnd(record.get("low")),
                        "close": thousands_to_vnd(float(record.get("close", 0))),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        if bars:
            series[ticker] = bars

    return series


async def compute_daily_return(ticker: str = "VNINDEX") -> float | None:
    """Compute latest daily % return for a ticker.

    Returns percentage change as whole number (e.g. 1.23 for +1.23%).
    Replaces v_daily_returns SQL view for consumers that only need the latest value.
    """
    result = await fetch_history_batch(
        symbols=[ticker.upper()],
        start=_start_date(5),
        end=_today(),
    )
    data = result.get(ticker.upper(), {})
    closes = _extract_closes(data)

    if len(closes) < 2:
        return None

    prev, curr = closes[-2], closes[-1]
    if prev <= 0:
        return None

    return round((curr - prev) / prev * 100, 2)


async def compute_relative_strength(
    tickers: list[str],
    window: int = 20,
) -> dict[str, float | None]:
    """Compute N-day relative strength vs VNINDEX for each ticker.

    RS = (ticker_return_Nd) / (vnindex_return_Nd)
    RS > 1 means outperforming, RS < 1 means underperforming.

    Replaces mv_relative_strength materialized view.

    Returns {ticker: rs_value | None}
    """
    if not tickers:
        return {}

    all_symbols = ["VNINDEX"] + [t.upper() for t in tickers]
    # Fetch window + buffer days to ensure we have enough trading days
    result = await fetch_history_batch(
        symbols=all_symbols,
        start=_start_date(window + 15),
        end=_today(),
    )

    vnindex_closes = _extract_closes(result.get("VNINDEX", {}))
    if len(vnindex_closes) < window + 1:
        return {t.upper(): None for t in tickers}

    vnindex_now = vnindex_closes[-1]
    vnindex_ago = vnindex_closes[-(window + 1)]
    if vnindex_ago <= 0:
        return {t.upper(): None for t in tickers}

    vnindex_return = vnindex_now / vnindex_ago

    rs: dict[str, float | None] = {}
    for ticker in tickers:
        ticker_upper = ticker.upper()
        closes = _extract_closes(result.get(ticker_upper, {}))

        if len(closes) < window + 1:
            rs[ticker_upper] = None
            continue

        now = closes[-1]
        ago = closes[-(window + 1)]
        if ago <= 0:
            rs[ticker_upper] = None
            continue

        ticker_return = now / ago
        rs[ticker_upper] = round(ticker_return / vnindex_return, 4)

    return rs
