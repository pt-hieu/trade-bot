"""
Midday check helper functions — deterministic pre-computation, no LLM calls.

All price data here comes from fetch_prices_async which returns thousands VND
from vnstock API. PRICE_MULTIPLIER converts to VND for DB storage and display.

`canonical_current_price_vnd` is the single source for "current price" across
Big Movers / Position Alerts / Afternoon Plan. The 2026-04-28 ACV mismatch
(44k in one section, 44.5k in another) came from helpers reading distinct
fields (`close` vs separate snapshot timestamps); routing every consumer
through this helper guarantees one timestamp per (scan, ticker).
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

from data.prices import fetch_prices_async
from shared.config import PRICE_MULTIPLIER
from shared.neon import get_swing_watchlist
from shared.watchlist import merge_holdings_into_watchlist


def canonical_current_price_vnd(price_data: dict | None) -> int | None:
    """Return the canonical VND-int current price for a ticker.

    Reads ``close`` from ``midday_prices[ticker]`` (k-VND scale) and
    multiplies by ``PRICE_MULTIPLIER``. Returns ``None`` when price is
    missing or non-positive — callers should skip the row instead of
    rendering a stale fallback.
    """
    if not price_data:
        return None
    raw_close = price_data.get("close") or 0
    if raw_close <= 0:
        return None
    return int(round(raw_close * PRICE_MULTIPLIER))


async def fetch_midday_prices(date_str: str, holdings_fetcher) -> dict:
    """Fetch midday prices — live partial-day bars if today, 15m historical if past date.

    Args:
        date_str: Date string in YYYY-MM-DD format.
        holdings_fetcher: Async callable returning holdings data dict.
    """
    from shared.config import get_scan_date

    today = get_scan_date()
    is_historical = date_str != today

    logger.info("Fetching midday prices for %s", date_str)
    watchlist, holdings_data = await asyncio.gather(get_swing_watchlist(), holdings_fetcher())
    if not watchlist:
        raise RuntimeError("Database unavailable - cannot fetch watchlist")

    # `holdings_data["holdings"]` may be list[HoldingData] (post-migration)
    # or the legacy dict-keyed shape from older fixtures — handle both.
    raw_holdings = holdings_data.get("holdings") or []
    if isinstance(raw_holdings, dict):
        held_list = [{"ticker": ticker} for ticker in raw_holdings]
    else:
        held_list = list(raw_holdings)
    watchlist = merge_holdings_into_watchlist(watchlist, held_list)

    if is_historical:
        from shared.vnstock_client import fetch_midday_snapshot

        all_tickers = [t for tickers in watchlist.values() for t in tickers]
        prices = await fetch_midday_snapshot(all_tickers, date_str)
        logger.info("Historical midday snapshot: %d tickers for %s", len(prices), date_str)
        return prices

    # Explicitly pass today's date to get live partial-day bars during market hours.
    # Default end_date is yesterday (completed bars only), so we must override.
    prices = await fetch_prices_async(watchlist, end_date=today)
    all_tickers = [t for tickers in watchlist.values() for t in tickers]
    if not prices:
        logger.warning(
            "fetch_prices_async returned empty for %d tickers: %s",
            len(all_tickers),
            all_tickers,
        )
    else:
        missing = [t for t in all_tickers if t not in prices]
        if missing:
            logger.warning("Missing midday prices for: %s", missing)
        logger.info("Midday prices fetched: %d/%d tickers", len(prices), len(all_tickers))
    return prices


def compute_entries_hit(recommendations: list[dict], midday_prices: dict) -> list[dict]:
    """Compare morning entry recs vs actual midday lows. Returns entries where low <= entry."""
    entries = []
    for rec in recommendations:
        ticker = rec.get("ticker", "")
        entry_price = rec.get("entry_price")
        action = rec.get("action", "").upper()

        if not entry_price or action not in ("BUY", "ADD"):
            continue

        price_data = midday_prices.get(ticker)
        if not price_data or "error" in price_data:
            continue

        canonical_current = canonical_current_price_vnd(price_data)
        if canonical_current is None:
            continue
        entry_k = entry_price / PRICE_MULTIPLIER
        actual_low = price_data.get("low", 0)
        hit = actual_low <= entry_k

        entries.append(
            {
                "ticker": ticker,
                "recommended_entry": entry_price,
                "actual_low": actual_low * PRICE_MULTIPLIER,
                "current_price": canonical_current,
                "status": (
                    f"PRICE REACHED entry level - Low {actual_low * PRICE_MULTIPLIER:,.0f} "
                    f"touched {entry_price:,.0f} (NOT yet bought, user decides)"
                    if hit
                    else f"MISSED - Low {actual_low * PRICE_MULTIPLIER:,.0f} above entry by "
                    f"{(actual_low - entry_k) / entry_k * 100:.1f}%"
                ),
            }
        )

    return [e for e in entries if "PRICE REACHED" in e["status"]]


def compute_big_movers(
    midday_prices: dict,
    threshold: float = 3.0,
    holdings_tickers: list[str] | None = None,
) -> list[dict]:
    """Find stocks with abs(change from prev_close) >= threshold %.

    Uses prev_close when available (captures overnight gaps).
    Falls back to open if prev_close missing.
    Holdings tickers are always included regardless of threshold.
    """
    holdings_set = set(holdings_tickers or [])
    movers = []
    for ticker, data in midday_prices.items():
        if "error" in data:
            continue
        canonical_current = canonical_current_price_vnd(data)
        if canonical_current is None:
            continue
        prev_close = data.get("prev_close", 0) or 0
        o = data.get("open", 0) or 0
        c = data.get("close", 0) or 0
        base = prev_close if prev_close > 0 else o
        if base <= 0:
            continue
        chg = (c - base) / base * 100
        if abs(chg) >= threshold or ticker in holdings_set:
            movers.append(
                {
                    "ticker": ticker,
                    "open_price": o * PRICE_MULTIPLIER,
                    "current_price": canonical_current,
                    "change_pct": round(chg, 1),
                    "direction": "UP" if chg >= 0 else "DOWN",
                }
            )
    return sorted(movers, key=lambda m: abs(m["change_pct"]), reverse=True)


def compute_position_alerts(
    recommendations: list[dict],
    midday_prices: dict,
    threshold: float = 2.0,
) -> list[dict]:
    """Check if any recommended positions are within threshold % of stop or target."""
    alerts = []
    for rec in recommendations:
        ticker = rec.get("ticker", "")
        stop = rec.get("stop_price")
        target = rec.get("target_price")

        price_data = midday_prices.get(ticker)
        if not price_data or "error" in price_data:
            continue
        canonical_current = canonical_current_price_vnd(price_data)
        if canonical_current is None:
            continue
        current = price_data.get("close", 0)
        if current <= 0:
            continue

        if stop:
            stop_k = stop / PRICE_MULTIPLIER
            low = price_data.get("low", current) or current
            if low <= stop_k:
                # Intraday touch (gap-down or intraday break). Distinct from
                # retro's STOP_BREACHED status (EOD close <= stop): an
                # intraday touch can still close above stop, so the two
                # carry different semantics. Renamed 2026-04-29 (SWI-140) to
                # surface the difference at the consumer layer.
                alerts.append(
                    {
                        "ticker": ticker,
                        "current_price": canonical_current,
                        "level": stop,
                        "level_type": "STOP_INTRADAY_TOUCH",
                        "distance_pct": round((current - stop_k) / current * 100, 1),
                        "urgency": "critical",
                    }
                )
            else:
                dist = (current - stop_k) / current * 100
                if 0 < dist <= threshold:
                    alerts.append(
                        {
                            "ticker": ticker,
                            "current_price": canonical_current,
                            "level": stop,
                            "level_type": "STOP",
                            "distance_pct": round(dist, 1),
                            "urgency": "high" if dist <= 1 else "medium",
                        }
                    )

        if target:
            target_k = target / PRICE_MULTIPLIER
            dist = (target_k - current) / current * 100
            if 0 < dist <= threshold:
                alerts.append(
                    {
                        "ticker": ticker,
                        "current_price": canonical_current,
                        "level": target,
                        "level_type": "TARGET",
                        "distance_pct": round(dist, 1),
                        "urgency": "high" if dist <= 1 else "medium",
                    }
                )
    return alerts
