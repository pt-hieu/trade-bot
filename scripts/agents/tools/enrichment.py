#!/usr/bin/env python3
"""Enrichment data tools: flow, insider, and relative strength.

Exposes daily_flow, insider_transactions, and mv_relative_strength
as registry-compatible agent tools.
"""

from datetime import date

# ============================================================================
# Internal async functions (return dict, used by Python code)
# ============================================================================


async def get_ticker_flow_async(ticker: str, scan_date: date) -> dict:
    """Get flow data for a ticker on a given scan date (from vnstock API)."""
    from shared.api.enrichment import get_daily_flow

    data = await get_daily_flow(ticker, scan_date)
    if not data:
        return {"ticker": ticker, "error": f"No flow data for {ticker} on {scan_date}"}
    return {"ticker": ticker, "scan_date": str(scan_date), **data}


async def get_batch_flow_async(tickers: list[str], scan_date: date) -> dict[str, dict]:
    """Get flow data for a batch of tickers in a single API call.

    Returns dict keyed by uppercased ticker. Missing/empty results are
    {"ticker": X, "error": "No flow data ..."}.
    """
    from shared.api.enrichment import get_daily_flow_batch

    raw = await get_daily_flow_batch(tickers, scan_date)
    result: dict[str, dict] = {}
    for ticker in tickers:
        key = ticker.upper()
        data = raw.get(key)
        if not data:
            result[key] = {"ticker": key, "error": f"No flow data for {key} on {scan_date}"}
            continue
        result[key] = {"ticker": key, "scan_date": str(scan_date), **data}
    return result


async def get_ticker_insider_async(ticker: str) -> list[dict]:
    """Get insider transactions (90d lookback) for a ticker (from vnstock API)."""
    from shared.api.enrichment import get_recent_insider_transactions

    return await get_recent_insider_transactions(ticker, lookback_days=90)


async def get_batch_insider_async(tickers: list[str]) -> dict[str, list[dict]]:
    """Get insider transactions (90d) for a batch of tickers in a single API call."""
    from shared.api.enrichment import get_recent_insider_transactions_batch

    return await get_recent_insider_transactions_batch(tickers, lookback_days=90)


async def get_ticker_rs_async(tickers: list[str], scan_date: date) -> dict[str, float | None]:
    """Get 20d RS vs VN-Index for a batch of tickers (single API round-trip)."""
    from shared.neon.enrichment import get_relative_strength

    return await get_relative_strength(tickers, scan_date)


async def get_sector_flow_aggregate_async(tickers: list[str], scan_date: date) -> dict:
    """Aggregate flow data by sector for a list of tickers.

    Returns aggregated foreign_net, prop_net, retail_net, order_imbalance
    and per-ticker breakdown. Single batch API call regardless of ticker count.
    """
    from shared.api.enrichment import get_daily_flow_batch
    from shared.neon import safe_float

    batch = await get_daily_flow_batch(tickers, scan_date)

    total_foreign = 0.0
    total_prop = 0.0
    total_retail = 0.0
    imbalances: list[float] = []
    ticker_flows: dict[str, dict] = {}

    for ticker_upper, data in batch.items():
        if not data:
            continue
        foreign_net = safe_float(data.get("foreign_net"))
        if foreign_net is not None:
            total_foreign += foreign_net
        prop_net = safe_float(data.get("prop_net"))
        if prop_net is not None:
            total_prop += prop_net
        retail_net = safe_float(data.get("retail_net"))
        if retail_net is not None:
            total_retail += retail_net
        order_imbalance = safe_float(data.get("order_imbalance"))
        if order_imbalance is not None:
            imbalances.append(order_imbalance)
        ticker_flows[ticker_upper] = data

    avg_imbalance = sum(imbalances) / len(imbalances) if imbalances else None
    return {
        "scan_date": str(scan_date),
        "tickers_with_data": len(ticker_flows),
        "foreign_net_total": total_foreign,
        "prop_net_total": total_prop,
        "retail_net_total": total_retail,
        "avg_order_imbalance": avg_imbalance,
        "ticker_flows": ticker_flows,
    }


# ============================================================================
# Agent tools (return prose str, for LLM agents via registry)
# ============================================================================


def _format_flow_prose(ticker: str, data: dict, scan_date: date) -> str:
    """Format a single ticker's flow data as LLM-consumable prose."""
    if "error" in data:
        return f"{ticker}: No flow data available for {scan_date}"

    foreign = data.get("foreign_net")
    prop = data.get("prop_net")
    retail = data.get("retail_net")
    imbalance = data.get("order_imbalance")

    parts = [f"{ticker} Flow ({scan_date}):"]
    if foreign is not None:
        direction = "NET BUY" if foreign > 0 else "NET SELL"
        parts.append(f"  Foreign: {direction} {abs(foreign) / 1e9:.1f}B VND")
    if prop is not None:
        prop_dir = "NET BUY" if prop > 0 else "NET SELL"
        parts.append(f"  Proprietary: {prop_dir} {abs(prop) / 1e9:.1f}B VND")
    if retail is not None:
        retail_dir = "NET BUY" if retail > 0 else "NET SELL"
        parts.append(f"  Retail (implied): {retail_dir} {abs(retail) / 1e9:.1f}B VND")
    if imbalance is not None:
        bias = (
            "buy-heavy" if imbalance > 0.1 else ("sell-heavy" if imbalance < -0.1 else "balanced")
        )
        parts.append(f"  Order imbalance: {imbalance:+.2f} ({bias})")
    if data.get("proprietary_note"):
        parts.append(f"  NOTE: {data['proprietary_note']} — do NOT fabricate flow numbers")

    return "\n".join(parts)


def _format_insider_prose(ticker: str, rows: list[dict]) -> str:
    """Format a single ticker's insider transactions as LLM-consumable prose."""
    if not rows:
        return f"{ticker}: No insider transactions in last 90 days."

    parts = [f"{ticker} Insider Activity (90d):"]
    buy_count = sum(1 for r in rows if (r.get("action") or "").upper() in ("BUY", "PURCHASE"))
    sell_count = sum(1 for r in rows if (r.get("action") or "").upper() == "SELL")
    parts.append(f"  {buy_count} buy registrations, {sell_count} sell registrations")

    for r in rows[:5]:
        name = (r.get("trader_name") or "Unknown")[:20]
        pos = (r.get("trader_position") or "")[:15]
        action = r.get("action") or "?"
        shares = r.get("shares_registered")
        start = str(r.get("start_date", ""))[:10]
        shares_str = f"{shares:,} shares" if shares else "pending registration"
        parts.append(f"  [{start}] {name} ({pos}): {action} {shares_str}")

    return "\n".join(parts)


async def tool_get_flow(tickers: list[str], scan_date: date | None = None) -> str:
    """Get foreign/prop/retail flow summary for a batch of tickers.

    Args:
        tickers: list of stock tickers (e.g., ['FPT', 'TCB'])
        scan_date: Date of flow data (defaults to today)
    """
    if not tickers:
        return "Error: no tickers provided"
    if scan_date is None:
        from datetime import date as date_type

        scan_date = date_type.today()

    batch = await get_batch_flow_async(tickers, scan_date)
    return "\n\n".join(
        _format_flow_prose(ticker, batch[ticker.upper()], scan_date) for ticker in tickers
    )


async def tool_get_insider(tickers: list[str]) -> str:
    """Get insider transaction activity (90d) for a batch of tickers.

    Args:
        tickers: list of stock tickers (e.g., ['FPT', 'TCB'])
    """
    if not tickers:
        return "Error: no tickers provided"

    batch = await get_batch_insider_async(tickers)
    return "\n\n".join(
        _format_insider_prose(ticker, batch.get(ticker.upper(), [])) for ticker in tickers
    )


def _rs_label(rs: float) -> str:
    if rs > 1.10:
        return "STRONG outperformer"
    if rs > 1.02:
        return "mild outperformer"
    if rs >= 0.98:
        return "in line with market"
    if rs >= 0.90:
        return "mild underperformer"
    return "WEAK underperformer"


async def tool_get_relative_strength(tickers: list[str], scan_date: date | None = None) -> str:
    """Get 20d relative strength vs VN-Index for a batch of tickers.

    Args:
        tickers: list of stock tickers (e.g., ['FPT', 'TCB'])
        scan_date: Date for RS lookup (defaults to today)
    """
    if not tickers:
        return "Error: no tickers provided"
    if scan_date is None:
        from datetime import date as date_type

        scan_date = date_type.today()

    rs_map = await get_ticker_rs_async([t.upper() for t in tickers], scan_date)

    lines: list[str] = []
    for ticker in tickers:
        rs = rs_map.get(ticker.upper())
        if rs is None:
            lines.append(f"{ticker}: No relative strength data available.")
            continue
        lines.append(f"{ticker} RS vs VN-Index (20d): {rs:.2f} — {_rs_label(rs)}")
    return "\n".join(lines)


async def tool_get_block_trades() -> str:
    """Get today's top block/deal trades by volume across the market.

    Block trades signal institutional conviction — large negotiated transactions
    outside the normal order book.
    """
    import logging

    logger = logging.getLogger(__name__)
    try:
        from shared.vnstock_client import fetch_market_deals

        deals = await fetch_market_deals(limit=20)
        if not deals:
            return "No block trade data available today."

        parts = ["Top Block Trades Today:"]
        for deal in deals[:10]:
            ticker = deal.get("ticker") or deal.get("symbol") or "?"
            # Try various field names the API might return
            volume = deal.get("total_volume") or deal.get("volume") or 0
            value = deal.get("total_value") or deal.get("value") or 0
            value_b = value / 1e9 if value else 0
            parts.append(f"  {ticker}: {value_b:.1f}B VND ({volume:,.0f} shares)")

        return "\n".join(parts)
    except Exception as e:
        logger.warning("tool_get_block_trades failed: %s", e)
        return f"Block trade data unavailable: {e}"
