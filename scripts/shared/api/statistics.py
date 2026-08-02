"""Statistical analysis — computed from vnstock API price history.

Replaces shared/neon/statistics.py — same function signatures, API-backed.
Fetches OHLCV + historical RSI from vnstock API, computes stats in Python.

Key difference from DB version:
- `get_pattern_outcome_stats` and `get_price_action_analysis` now require `ticker`
  (old DB version was cross-ticker; API version is per-ticker)
- `get_rsi_oversold_bounces` and `get_consecutive_pattern_days` signatures unchanged
"""

from datetime import datetime, timedelta

import pandas as pd

from data.technicals import (
    calculate_closed_at_low,
    calculate_volume_vs_avg,
    detect_candlestick_patterns,
)

from ..vnstock_client import fetch_history_batch, fetch_technicals_history

# ── Helpers ───────────────────────────────────────────────────────────────────


def _start_date(days: int) -> str:
    """Start date with buffer for weekends, holidays, and RSI warmup (14-day)."""
    return (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


async def _fetch_ohlcv_and_rsi(
    ticker: str,
    days_back: int,
) -> tuple[list[dict], dict[str, float]]:
    """Fetch OHLCV records and RSI-per-date for a ticker.

    Returns:
        (ohlcv_records, rsi_by_date) where rsi_by_date = {date_str: rsi_float}
    """
    ticker_upper = ticker.upper()
    start = _start_date(days_back)
    end = _today()

    ohlcv_result = await fetch_history_batch(
        symbols=[ticker_upper],
        start=start,
        end=end,
    )

    ohlcv_records: list[dict] = []
    raw = ohlcv_result.get(ticker_upper, {})
    if isinstance(raw, dict) and "error" not in raw:
        ohlcv_records = raw.get("data", [])

    rsi_result = await fetch_technicals_history(
        symbol=ticker_upper,
        start=start,
        end=end,
    )

    rsi_by_date: dict[str, float] = {}
    for r in rsi_result.get("data", []):
        try:
            date_str = str(r.get("date") or r.get("time", ""))[:10]
            rsi_val = r.get("rsi")
            if date_str and rsi_val is not None:
                rsi_by_date[date_str] = float(rsi_val)
        except (TypeError, ValueError):
            continue

    return ohlcv_records, rsi_by_date


def _next_day_changes(ohlcv_records: list[dict]) -> dict[str, float | None]:
    """Build {date_str: next_trading_day_change_pct} from OHLCV records.

    Returns None for the last record (no next day available).
    """
    changes: dict[str, float | None] = {}
    for i, rec in enumerate(ohlcv_records):
        date_str = str(rec.get("time", ""))[:10]
        if not date_str:
            continue
        if i + 1 < len(ohlcv_records):
            try:
                curr_close = float(rec["close"])
                next_close = float(ohlcv_records[i + 1]["close"])
                if curr_close > 0:
                    changes[date_str] = round((next_close - curr_close) / curr_close * 100, 4)
                else:
                    changes[date_str] = None
            except (KeyError, TypeError, ValueError):
                changes[date_str] = None
        else:
            changes[date_str] = None  # Last day has no next day
    return changes


def _pattern_per_day(ohlcv_records: list[dict]) -> dict[str, str | None]:
    """Detect candlestick pattern for each day using rolling window.

    For day N, uses candles df[:N+1] so pattern detection sees prior candle.
    Returns {date_str: pattern_name | None}
    """
    df = pd.DataFrame(ohlcv_records)
    if df.empty or "close" not in df.columns:
        return {}

    patterns: dict[str, str | None] = {}
    for i in range(len(df)):
        date_str = str(df.iloc[i].get("time", ""))[:10]
        if not date_str:
            continue
        window = df.iloc[: i + 1]
        result = detect_candlestick_patterns(window)
        patterns[date_str] = result.get("pattern")

    return patterns


# ── Public functions ──────────────────────────────────────────────────────────


async def get_rsi_oversold_bounces(
    ticker: str | None = None,
    rsi_threshold: float = 30.0,
    days_back: int = 90,
) -> dict:
    """RSI oversold stats: bounce_rate, avg_next_day_change, max_consecutive.

    Replaces DB query against daily_technicals + daily_records join.
    When ticker is None, returns empty stats (cross-ticker analysis requires DB).
    """
    if not ticker:
        return {
            "ticker": ticker,
            "rsi_threshold": rsi_threshold,
            "days_back": days_back,
            "total_occurrences": 0,
            "bounce_rate": 0,
            "avg_next_day_change": 0,
            "max_consecutive_oversold": 0,
        }

    ohlcv_records, rsi_by_date = await _fetch_ohlcv_and_rsi(ticker, days_back)
    if not ohlcv_records:
        return {
            "ticker": ticker,
            "rsi_threshold": rsi_threshold,
            "days_back": days_back,
            "total_occurrences": 0,
            "bounce_rate": 0,
            "avg_next_day_change": 0,
            "max_consecutive_oversold": 0,
        }

    next_changes = _next_day_changes(ohlcv_records)

    # Filter to days within days_back and where RSI < threshold
    cutoff = datetime.now() - timedelta(days=days_back)
    qualifying_dates = []
    for date_str, rsi in rsi_by_date.items():
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if day >= cutoff and rsi < rsi_threshold:
            qualifying_dates.append(date_str)

    if not qualifying_dates:
        return {
            "ticker": ticker,
            "rsi_threshold": rsi_threshold,
            "days_back": days_back,
            "total_occurrences": 0,
            "bounce_rate": 0,
            "avg_next_day_change": 0,
            "max_consecutive_oversold": 0,
        }

    total = len(qualifying_dates)
    changes: list[float] = [v for d in qualifying_dates if (v := next_changes.get(d)) is not None]
    bounces = sum(1 for c in changes if c > 0)
    avg_change = sum(changes) / len(changes) if changes else 0

    # Max consecutive oversold days
    sorted_dates = sorted(qualifying_dates)
    max_consecutive = 1
    streak = 1
    for i in range(1, len(sorted_dates)):
        d_prev = datetime.strptime(sorted_dates[i - 1], "%Y-%m-%d")
        d_curr = datetime.strptime(sorted_dates[i], "%Y-%m-%d")
        if (d_curr - d_prev).days <= 3:  # Allow weekend gaps
            streak += 1
            max_consecutive = max(max_consecutive, streak)
        else:
            streak = 1

    return {
        "ticker": ticker,
        "rsi_threshold": rsi_threshold,
        "days_back": days_back,
        "total_occurrences": total,
        "bounce_rate": round(bounces / total, 2) if total else 0,
        "avg_next_day_change": round(avg_change, 2),
        "max_consecutive_oversold": max_consecutive,
    }


async def get_pattern_outcome_stats(
    pattern: str,
    rsi_min: float = 0,
    rsi_max: float = 100,
    days_back: int = 90,
    ticker: str | None = None,
) -> dict:
    """Win rates for candlestick patterns (hammer, doji, engulfing, etc.).

    NOTE: ticker is required for API version. Without ticker, returns empty stats.
    Old DB version was cross-ticker; supply ticker for meaningful results.
    """
    if not ticker:
        return {
            "pattern": pattern,
            "rsi_range": [rsi_min, rsi_max],
            "days_back": days_back,
            "occurrences": 0,
            "win_rate": 0,
            "avg_move": 0,
            "best_rsi_zone": None,
        }

    ohlcv_records, rsi_by_date = await _fetch_ohlcv_and_rsi(ticker, days_back)
    if not ohlcv_records:
        return {
            "pattern": pattern,
            "rsi_range": [rsi_min, rsi_max],
            "days_back": days_back,
            "occurrences": 0,
            "win_rate": 0,
            "avg_move": 0,
            "best_rsi_zone": None,
        }

    next_changes = _next_day_changes(ohlcv_records)
    patterns_by_date = _pattern_per_day(ohlcv_records)

    cutoff = datetime.now() - timedelta(days=days_back)
    rows = []
    for date_str, pat in patterns_by_date.items():
        if pat != pattern:
            continue
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if day < cutoff:
            continue
        rsi = rsi_by_date.get(date_str)
        if rsi is not None and not (rsi_min <= rsi <= rsi_max):
            continue
        rows.append({"date": date_str, "rsi": rsi, "change": next_changes.get(date_str)})

    if not rows:
        return {
            "pattern": pattern,
            "rsi_range": [rsi_min, rsi_max],
            "days_back": days_back,
            "occurrences": 0,
            "win_rate": 0,
            "avg_move": 0,
            "best_rsi_zone": None,
        }

    total = len(rows)
    wins = sum(1 for r in rows if r["change"] is not None and r["change"] > 0)
    changes = [r["change"] for r in rows if r["change"] is not None]
    avg_move = sum(changes) / len(changes) if changes else 0

    rsi_zones: dict[str, list] = {"0-30": [], "30-50": [], "50-70": [], "70-100": []}
    for r in rows:
        if r["rsi"] is not None and r["change"] is not None:
            rsi = r["rsi"]
            zone = (
                "0-30" if rsi < 30 else "30-50" if rsi < 50 else "50-70" if rsi < 70 else "70-100"
            )
            rsi_zones[zone].append(r["change"])

    zone_avgs = {z: sum(v) / len(v) for z, v in rsi_zones.items() if v}
    best_zone = max(zone_avgs, key=lambda k: zone_avgs[k]) if zone_avgs else None

    return {
        "pattern": pattern,
        "rsi_range": [rsi_min, rsi_max],
        "days_back": days_back,
        "occurrences": total,
        "win_rate": round(wins / total, 2) if total else 0,
        "avg_move": round(avg_move, 2),
        "best_rsi_zone": best_zone,
    }


async def get_price_action_analysis(
    ticker: str | None = None,
    days_back: int = 30,
) -> dict:
    """Closed-at-low reversal rates, overall and with high volume.

    NOTE: ticker required for API version. Old DB version was cross-ticker.
    """
    if not ticker:
        return {
            "days_back": days_back,
            "closed_at_low_count": 0,
            "reversal_rate": 0,
            "with_high_volume": {"count": 0, "reversal_rate": 0},
        }

    ohlcv_records, rsi_by_date = await _fetch_ohlcv_and_rsi(ticker, days_back)
    if not ohlcv_records:
        return {
            "days_back": days_back,
            "closed_at_low_count": 0,
            "reversal_rate": 0,
            "with_high_volume": {"count": 0, "reversal_rate": 0},
        }

    df = pd.DataFrame(ohlcv_records)
    next_changes = _next_day_changes(ohlcv_records)
    cutoff = datetime.now() - timedelta(days=days_back)

    rows = []
    for i, rec in enumerate(ohlcv_records):
        date_str = str(rec.get("time", ""))[:10]
        if not date_str:
            continue
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if day < cutoff:
            continue

        try:
            closed_low = calculate_closed_at_low(
                high=float(rec["high"]),
                low=float(rec["low"]),
                close=float(rec["close"]),
            )
        except (KeyError, TypeError, ValueError):
            continue

        if not closed_low:
            continue

        vol_vs_avg = calculate_volume_vs_avg(df.iloc[: i + 1], window=20)
        rsi = rsi_by_date.get(date_str)
        change = next_changes.get(date_str)
        rows.append({"date": date_str, "rsi": rsi, "vol_vs_avg": vol_vs_avg, "change": change})

    if not rows:
        return {
            "days_back": days_back,
            "closed_at_low_count": 0,
            "reversal_rate": 0,
            "with_high_volume": {"count": 0, "reversal_rate": 0},
        }

    total = len(rows)
    reversals = sum(1 for r in rows if r["change"] is not None and r["change"] > 0)

    high_vol = [r for r in rows if r["vol_vs_avg"] is not None and r["vol_vs_avg"] > 1.5]
    high_vol_rev = sum(1 for r in high_vol if r["change"] is not None and r["change"] > 0)

    by_rsi: dict[str, list[bool]] = {
        "oversold_0_30": [],
        "neutral_30_50": [],
        "overbought_50_plus": [],
    }
    for r in rows:
        if r["rsi"] is not None and r["change"] is not None:
            rsi = r["rsi"]
            bounced = r["change"] > 0
            zone = (
                "oversold_0_30"
                if rsi < 30
                else "neutral_30_50"
                if rsi < 50
                else "overbought_50_plus"
            )
            by_rsi[zone].append(bounced)

    by_rsi_rates = {
        z: {"count": len(v), "reversal_rate": round(sum(v) / len(v), 2)}
        for z, v in by_rsi.items()
        if v
    }

    return {
        "days_back": days_back,
        "closed_at_low_count": total,
        "reversal_rate": round(reversals / total, 2) if total else 0,
        "with_high_volume": {
            "count": len(high_vol),
            "reversal_rate": round(high_vol_rev / len(high_vol), 2) if high_vol else 0,
        },
        "by_rsi_zone": by_rsi_rates,
    }


async def get_consecutive_pattern_days(
    ticker: str,
    condition: str,
    days_back: int = 90,
) -> dict:
    """Consecutive days meeting condition (rsi_below_30, rsi_below_20, closed_at_low)."""
    if condition not in ("rsi_below_30", "rsi_below_20", "closed_at_low"):
        return {"error": f"Unknown condition: {condition}"}

    ohlcv_records, rsi_by_date = await _fetch_ohlcv_and_rsi(ticker, days_back)
    if not ohlcv_records:
        return {
            "ticker": ticker,
            "condition": condition,
            "days_back": days_back,
            "total_days": 0,
            "max_consecutive": 0,
            "current_streak": 0,
        }

    cutoff = datetime.now() - timedelta(days=days_back)

    qualifying: list[datetime] = []
    for _i, rec in enumerate(ohlcv_records):
        date_str = str(rec.get("time", ""))[:10]
        if not date_str:
            continue
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if day < cutoff:
            continue

        if condition in ("rsi_below_30", "rsi_below_20"):
            threshold = 30.0 if condition == "rsi_below_30" else 20.0
            rsi = rsi_by_date.get(date_str)
            if rsi is not None and rsi < threshold:
                qualifying.append(day)
        elif condition == "closed_at_low":
            try:
                is_low = calculate_closed_at_low(
                    high=float(rec["high"]),
                    low=float(rec["low"]),
                    close=float(rec["close"]),
                )
                if is_low:
                    qualifying.append(day)
            except (KeyError, TypeError, ValueError):
                continue

    if not qualifying:
        return {
            "ticker": ticker,
            "condition": condition,
            "days_back": days_back,
            "total_days": 0,
            "max_consecutive": 0,
            "avg_consecutive": 0,
            "distribution": {},
            "current_streak": 0,
        }

    # Compute streaks
    streaks: list[int] = []
    current = 1
    for i in range(1, len(qualifying)):
        gap = (qualifying[i] - qualifying[i - 1]).days
        if gap <= 3:  # Allow up to 3 days (weekends + 1 holiday)
            current += 1
        else:
            streaks.append(current)
            current = 1
    streaks.append(current)

    # Active streak: is the last qualifying day within 3 days of today?
    days_since_last = (datetime.now() - qualifying[-1]).days
    active_streak = streaks[-1] if days_since_last <= 3 else 0

    distribution: dict[int, int] = {}
    for s in streaks:
        distribution[s] = distribution.get(s, 0) + 1

    return {
        "ticker": ticker,
        "condition": condition,
        "days_back": days_back,
        "total_days": len(qualifying),
        "max_consecutive": max(streaks),
        "avg_consecutive": round(sum(streaks) / len(streaks), 1),
        "distribution": distribution,
        "current_streak": active_streak,
    }
