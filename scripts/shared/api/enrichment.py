"""Enrichment data (flow, insider, corporate events) — reads from vnstock API.

Replaces shared.neon.enrichment for flow/insider/events read operations.
Same function signatures as neon module — consumers change only their import path.

Note: get_relative_strength() is NOT here — it's computed from mv_relative_strength
materialized view (historical RS vs VN-Index). Use shared.neon.enrichment for that.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

import anyio

from ..lint_markers import allow_single_ticker_fetcher
from ..vnstock_client import fetch_ticker_enrichment as _fetch_enrichment

logger = logging.getLogger(__name__)


class EnrichmentTimeout(Exception):
    """Typed wall-clock timeout from the enrichment API (SWI-125 Surface 5b).

    Raised by ``get_daily_flow_batch`` / ``get_recent_insider_transactions_batch``
    so the model-hop wrapper (SWI-115) can tag the span instead of the
    previous silent empty-dict fallback. Non-timeout transient failures
    still take the empty-dict fallback with ``logger.warning(exc_info=True)``.
    """


_TIMEOUT_EXC_TYPES: tuple[type[BaseException], ...] = (
    TimeoutError,
    asyncio.TimeoutError,
    anyio.EndOfStream,
)

# ── Internal helpers ──────────────────────────────────────────────────────────


def _latest_val(records: list, *keys: str) -> float | None:
    """Extract most recent non-None numeric value for any of the given keys.

    API returns records sorted desc by date — first non-None match is latest.
    Accepts multiple key names to handle camelCase/snake_case variants.
    """
    for record in records:
        for key in keys:
            v = record.get(key)
            if v is not None:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    continue
    return None


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def _clean_list(data) -> list:
    """Return data if it's a usable list, empty list otherwise."""
    if isinstance(data, list):
        return data
    return []


# ── Public functions (same interface as shared.neon.enrichment) ───────────────


def _parse_flow_modules(modules: dict) -> dict[str, float | str | None] | None:
    """Decode flow+prop+orders module data for one ticker into the flat schema."""
    flow_data = _clean_list(modules.get("flow"))
    prop_data = _clean_list(modules.get("prop"))
    orders_data = _clean_list(modules.get("orders"))

    if not flow_data and not prop_data and not orders_data:
        return None

    # API field names: flow uses fr_net_value; prop has no net field — compute from buy/sell.
    # SWI-299: the 3-day flow window can include a CURRENT-day pre-market
    # placeholder row (foreign buy/sell/net all 0), sorted ahead of the latest
    # real trading day. The morning scan runs pre-open, so picking the latest
    # row by date pegged foreign_net to 0 on 100% of candidates. Prefer the
    # latest row with ACTUAL foreign activity (any non-zero buy/sell/net); a
    # genuinely balanced real day (buy & sell non-zero, net≈0) is retained. When
    # no row shows activity, foreign_net stays None (honest no-data, not a
    # fabricated zero).
    active_flow_data = [
        record
        for record in flow_data
        if (record.get("fr_buy_value") or 0)
        or (record.get("fr_sell_value") or 0)
        or (record.get("fr_net_value") or 0)
    ]
    foreign_net = _latest_val(active_flow_data, "fr_net_value")
    prop_buy = _latest_val(prop_data, "prop_buy_value")
    prop_sell = _latest_val(prop_data, "prop_sell_value")
    prop_available = prop_buy is not None and prop_sell is not None
    prop_net = (prop_buy - prop_sell) if (prop_buy is not None and prop_sell is not None) else None
    buy_orders = _latest_val(orders_data, "buy_orders")
    sell_orders = _latest_val(orders_data, "sell_orders")

    implied_retail = None
    if foreign_net is not None and prop_net is not None:
        implied_retail = -(foreign_net + prop_net)

    order_imbalance = None
    if buy_orders is not None and sell_orders is not None:
        total = buy_orders + sell_orders
        if total > 0:
            order_imbalance = (buy_orders - sell_orders) / total

    result: dict[str, float | str | None] = {
        "foreign_net": foreign_net,
        "prop_net": prop_net,
        "retail_net": implied_retail,
        "order_imbalance": order_imbalance,
    }
    if not prop_available and foreign_net is not None:
        result["proprietary_note"] = (
            "CafeF does not provide proprietary trading data for this ticker"
        )
    return result


def _parse_insider_module(insider_data: list, lookback_days: int) -> list[dict]:
    """Decode insider module data for one ticker into filtered transaction list."""
    cutoff = date.today() - timedelta(days=lookback_days)
    result: list[dict] = []
    for row in insider_data:
        start_date = _parse_date(row.get("startDate") or row.get("start_date"))
        if not start_date or start_date < cutoff:
            continue

        action_raw = str(row.get("action") or row.get("dealAction") or "")
        action = "BUY" if "buy" in action_raw.lower() or "mua" in action_raw.lower() else "SELL"

        result.append(
            {
                "trader_name": row.get("traderName") or row.get("trader_name"),
                "trader_position": row.get("traderPosition") or row.get("trader_position"),
                "action": action,
                "shares_registered": row.get("sharesRegistered") or row.get("shares_registered"),
                "start_date": start_date,
            }
        )

    return result[:10]  # match DB query LIMIT 10


async def get_daily_flow_batch(
    tickers: list[str], scan_date: date | None = None
) -> dict[str, dict[str, float | str | None] | None]:
    """Get foreign/prop/retail flow for a batch of tickers (single API call).

    scan_date param kept for interface compat — ignored, API returns latest.
    Returns dict keyed by uppercased ticker mapping to flow dict or None.
    """
    normalized = [ticker.upper() for ticker in tickers]
    try:
        enrichment = await _fetch_enrichment(
            symbols=normalized,
            modules=["flow", "prop", "orders"],
            days=3,
        )
    except _TIMEOUT_EXC_TYPES as exc:
        raise EnrichmentTimeout(
            f"get_daily_flow_batch timed out for {len(normalized)} tickers: {exc}"
        ) from exc
    except Exception as exc:
        logger.warning(
            "get_daily_flow_batch failed for %d tickers: %s",
            len(normalized),
            exc,
            exc_info=True,
        )
        return dict.fromkeys(normalized)

    return {ticker: _parse_flow_modules(enrichment.get(ticker) or {}) for ticker in normalized}


async def get_recent_insider_transactions_batch(
    tickers: list[str], lookback_days: int = 90
) -> dict[str, list[dict]]:
    """Get recent insider transactions for a batch of tickers (single API call).

    Returns dict keyed by uppercased ticker mapping to list of transaction dicts
    (empty list if none). Each transaction has trader_name, trader_position,
    action, shares_registered, start_date.
    """
    normalized = [ticker.upper() for ticker in tickers]
    try:
        enrichment = await _fetch_enrichment(
            symbols=normalized,
            modules=["insider"],
            days=5,
        )
    except _TIMEOUT_EXC_TYPES as exc:
        raise EnrichmentTimeout(
            f"get_recent_insider_transactions_batch timed out for {len(normalized)} tickers: {exc}"
        ) from exc
    except Exception as exc:
        logger.warning(
            "get_recent_insider_transactions_batch failed for %d tickers: %s",
            len(normalized),
            exc,
            exc_info=True,
        )
        return {ticker: [] for ticker in normalized}

    return {
        ticker: _parse_insider_module(
            _clean_list((enrichment.get(ticker) or {}).get("insider")), lookback_days
        )
        for ticker in normalized
    }


async def get_daily_flow(ticker: str, scan_date: date | None = None) -> dict | None:
    """Get foreign/prop/retail flow for a single ticker (delegates to batch)."""
    result = await get_daily_flow_batch([ticker], scan_date)
    return result.get(ticker.upper())


async def get_recent_insider_transactions(ticker: str, lookback_days: int = 90) -> list[dict]:
    """Get recent insider transactions for a single ticker (delegates to batch)."""
    result = await get_recent_insider_transactions_batch([ticker], lookback_days)
    return result.get(ticker.upper(), [])


@allow_single_ticker_fetcher  # vnstock events API is single-symbol; no batch HTTP endpoint
async def get_upcoming_corporate_events(
    ticker: str,
    scan_date: date | None = None,
    lookahead_days: int = 30,
) -> list[dict]:
    """Get upcoming corporate events for a ticker (from vnstock API).

    scan_date param kept for interface compat; defaults to today.
    Returns list of {event_type, event_title, ex_date, value}.
    Same shape as shared.neon.enrichment.get_upcoming_corporate_events().
    """
    ref_date = scan_date or date.today()
    cutoff = ref_date + timedelta(days=lookahead_days)
    _SENTINEL = "1753-01-01"

    try:
        enrichment = await _fetch_enrichment(
            symbols=[ticker.upper()],
            modules=["events"],
            days=5,
        )
    except Exception:
        return []

    events_data = _clean_list((enrichment.get(ticker.upper()) or {}).get("events"))
    if not events_data:
        return []

    result = []
    for row in events_data:
        ex_date_str = row.get("exDate") or row.get("ex_date") or row.get("exright_date")
        if not ex_date_str or str(ex_date_str)[:10] == _SENTINEL:
            continue
        ex_date = _parse_date(ex_date_str)
        if not ex_date or ex_date < ref_date or ex_date > cutoff:
            continue

        event_type = str(
            row.get("eventType")
            or row.get("event_type")
            or row.get("event_list_code")
            or row.get("event_list_name")
            or "unknown"
        ).lower()
        value_raw = row.get("value") or row.get("cashDividend") or row.get("ratio")
        value = float(value_raw) if value_raw else None

        result.append(
            {
                "event_type": event_type,
                "event_title": row.get("eventTitle") or row.get("event_title") or row.get("title"),
                "ex_date": ex_date,
                "value": value,
            }
        )

    return result[:5]  # match DB query LIMIT 5
