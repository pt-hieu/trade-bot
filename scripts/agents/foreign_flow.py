#!/usr/bin/env python3
"""
Foreign Flow Agent.

Fetches foreign investor trading data via vnstock_data (Lightsail API).
Enriches with per-ticker buy/sell breakdown, ownership %, and remaining room.
"""

import asyncio
from datetime import date, timedelta

from pydantic import BaseModel

from shared.errors import report_caught
from shared.market_calendar import is_trading_day


class TopStock(BaseModel):
    """Stock in top bought/sold list."""

    ticker: str
    value_billion: float


class HoldingFlow(BaseModel):
    """Per-holding foreign flow detail."""

    ticker: str
    buy_value_billion: float
    sell_value_billion: float
    net_value_billion: float
    ownership_pct: float | None = None
    remaining_room: int | None = None
    near_limit: bool = False


NEAR_LIMIT_THRESHOLD = 45.0  # ownership % where foreigners face buying ceiling


def _get_previous_trading_day(ref_date: date) -> date:
    """Get previous trading day (skip weekends and holidays)."""
    prev = ref_date - timedelta(days=1)
    while not is_trading_day(prev):
        prev -= timedelta(days=1)
    return prev


def _parse_top_list(items: list[dict], limit: int = 5) -> list[dict]:
    """Parse top bought/sold items from API response."""
    result = []
    for item in items[:limit]:
        ticker = item.get("ticker") or item.get("symbol") or ""
        raw = item.get("value") or item.get("net_value") or 0
        if ticker:
            magnitude = abs(float(raw))
            vb = magnitude / 1e9 if magnitude > 1e6 else magnitude
            result.append({"ticker": ticker, "value_billion": round(vb, 3)})
    return result


async def _fetch_flow_data(
    holding_tickers: list[str],
    flow_date: str | None = None,
) -> dict:
    """Fetch foreign flow data: top bought/sold + per-holding details.

    Args:
        holding_tickers: Tickers to get per-holding detail for.
        flow_date: Trading date (YYYY-MM-DD) to query. None = server default.
    """
    from shared.vnstock_client import fetch_foreign_top

    top = await fetch_foreign_top(limit=10, date=flow_date)
    top_bought = _parse_top_list(top.get("top_bought", []))
    top_sold = _parse_top_list(top.get("top_sold", []))

    # Fetch per-ticker flow for holdings
    holding_details = []
    if holding_tickers:
        try:
            from shared.vnstock_client import fetch_foreign_flow

            per_stock = await fetch_foreign_flow(
                holding_tickers,
                end=flow_date,
            )
            holding_details = _build_holding_details(per_stock)
        except Exception as e:
            report_caught("foreign_flow.per_ticker", e)

    return {
        "top_bought": top_bought,
        "top_sold": top_sold,
        "holding_details": holding_details,
    }


def _unwrap_ticker_data(raw: dict) -> dict | None:
    """Unwrap per-ticker API response: {data: [{...}], count} -> inner dict."""
    if not isinstance(raw, dict):
        return None
    if "error" in raw:
        return None
    rows = raw.get("data", [])
    if rows and isinstance(rows, list):
        return rows[0]
    # Flat format (already unwrapped)
    if "fr_net_value" in raw:
        return raw
    return None


def _build_holding_details(per_stock: dict) -> list[dict]:
    """Build holding detail dicts from per-stock API response."""
    details = []
    for ticker, raw in per_stock.items():
        data = _unwrap_ticker_data(raw)
        if not data:
            continue
        buy_val = float(data.get("fr_buy_value", 0) or 0) / 1e9
        sell_val = float(data.get("fr_sell_value", 0) or 0) / 1e9
        net_val = float(data.get("fr_net_value", 0) or 0) / 1e9
        ownership = data.get("fr_ownership")
        room = data.get("fr_remaining_room")

        own_pct = float(ownership) if ownership is not None else None
        remaining = int(room) if room is not None else None

        details.append(
            HoldingFlow(
                ticker=ticker,
                buy_value_billion=round(buy_val, 3),
                sell_value_billion=round(sell_val, 3),
                net_value_billion=round(net_val, 3),
                ownership_pct=own_pct,
                remaining_room=remaining,
                near_limit=own_pct is not None and own_pct >= NEAR_LIMIT_THRESHOLD,
            ).model_dump()
        )
    return details


def _classify_flow(
    top_bought: list[dict],
    top_sold: list[dict],
) -> tuple[str, str]:
    """Classify foreign flow signal and pattern."""
    total_bought = sum(s.get("value_billion", 0) for s in top_bought)
    total_sold = sum(s.get("value_billion", 0) for s in top_sold)
    net = total_bought - total_sold

    if net > 50:
        signal = "RISK_ON"
    elif net < -50:
        signal = "RISK_OFF"
    else:
        signal = "NEUTRAL"

    if net > 100:
        pattern = "Accumulation"
    elif net < -100:
        pattern = "Distribution"
    else:
        pattern = "Neutral"

    return signal, pattern


async def fetch_flow_with_agent(scan_date: date | None = None) -> dict:
    """Fetch and analyze foreign flow with per-holding enrichment.

    Returns:
        Dict with flow data, holding details, and LLM interpretation.
    """
    if scan_date is None:
        scan_date = date.today()

    date_str = scan_date.strftime("%Y-%m-%d")

    # Query previous trading day (scan runs before market open)
    flow_date = _get_previous_trading_day(scan_date)
    flow_date_str = flow_date.strftime("%Y-%m-%d")
    print(f"  [Foreign] Querying flow for {flow_date_str} (prev trading day of {date_str})")

    try:
        # Step 1: Get holding tickers
        from shared.neon.portfolio import tickers_held

        from .tools.portfolio import get_holdings_async

        holdings_wrapper = await get_holdings_async()
        if "error" in holdings_wrapper:
            holding_tickers: list[str] = []
        else:
            slices: list[dict] = holdings_wrapper.get("holdings") or []
            holding_tickers = tickers_held(slices)

        # Step 2: Fetch top + per-holding data (previous trading day)
        data = await _fetch_flow_data(holding_tickers, flow_date=flow_date_str)
        top_bought = data["top_bought"]
        top_sold = data["top_sold"]
        holding_details = data["holding_details"]

        # Step 3: Classify
        signal, pattern = _classify_flow(top_bought, top_sold)

        # Step 4: Find matches
        all_flow_tickers = [s["ticker"] for s in top_bought + top_sold]
        matches = [t for t in holding_tickers if t in all_flow_tickers]

        # Step 5: Calculate totals
        buy_total = sum(s.get("value_billion", 0) for s in top_bought)
        sell_total = sum(s.get("value_billion", 0) for s in top_sold)
        net = buy_total - sell_total

        # Step 6: Generate interpretation
        interpretation = await _generate_interpretation(
            date_str,
            net,
            buy_total,
            sell_total,
            top_bought,
            top_sold,
            holding_details,
            signal,
            pattern,
            matches,
        )

        return {
            "date": date_str,
            "net_value_billion": round(net, 2),
            "buy_value_billion": round(buy_total, 2),
            "sell_value_billion": round(sell_total, 2),
            "top_bought": [TopStock(**s).model_dump() for s in top_bought[:5]],
            "top_sold": [TopStock(**s).model_dump() for s in top_sold[:5]],
            "holding_details": holding_details,
            "signal": signal,
            "pattern": pattern,
            "interpretation": interpretation,
            "watchlist_matches": matches,
        }
    except Exception as e:
        return {
            "error": f"Foreign flow fetch failed: {e}",
            "date": date_str,
            "signal": "NEUTRAL",
            "interpretation": f"Unable to fetch foreign flow data: {e}",
        }


async def _generate_interpretation(
    date_str: str,
    net: float,
    buy_total: float,
    sell_total: float,
    top_bought: list,
    top_sold: list,
    holding_details: list,
    signal: str,
    pattern: str,
    matches: list,
) -> str:
    """Use LLM to generate human-readable interpretation."""
    from shared.config import LLM_MODEL
    from shared.llm import call_llm

    bought_str = ", ".join(f"{s['ticker']}({s['value_billion']:.1f}B)" for s in top_bought[:5])
    sold_str = ", ".join(f"{s['ticker']}({s['value_billion']:.1f}B)" for s in top_sold[:5])

    # Build per-holding context
    holdings_lines = []
    for h in holding_details:
        line = f"- {h['ticker']}: Net {h['net_value_billion']:+.1f}B VND"
        line += f" (Buy: {h['buy_value_billion']:.1f}B, Sell: {h['sell_value_billion']:.1f}B)"
        if h.get("ownership_pct") is not None:
            line += f" | Own: {h['ownership_pct']:.1f}%"
        if h.get("remaining_room") is not None:
            line += f" | Room: {h['remaining_room']:,} shares"
        if h.get("near_limit"):
            line += " ⚠️ NEAR LIMIT"
        holdings_lines.append(line)

    holdings_block = ""
    if holdings_lines:
        holdings_block = "\n\nHoldings foreign activity:\n" + "\n".join(holdings_lines)

    prompt = f"""Foreign investor flow for {date_str}:

Net: {net:+.1f}B VND (Buy: {buy_total:.1f}B, Sell: {sell_total:.1f}B)
Signal: {signal}
Pattern: {pattern}
Top bought: {bought_str}
Top sold: {sold_str}
Portfolio matches: {", ".join(matches) if matches else "None"}{holdings_block}

This is PREVIOUS trading day data (scan runs before market open).
Write 2-3 sentences about what this means for Vietnamese stock trading today.
Focus on: institutional sentiment, sector preferences, impact on holdings.
If any holdings are near foreign ownership limit (>45%), flag the ceiling risk."""

    try:
        return await asyncio.to_thread(
            call_llm,
            "You are a foreign flow analyst for Vietnamese stocks. Be concise.",
            prompt,
            model=LLM_MODEL,
        )
    except Exception:
        return f"Foreign flow {signal}: Net {net:+.1f}B VND. {pattern}."
