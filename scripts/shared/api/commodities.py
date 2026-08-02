"""Commodity price data — API-first normalization layer."""

import logging

from shared.vnstock_client import fetch_commodity_prices as _fetch

logger = logging.getLogger(__name__)


async def get_commodity_prices() -> dict[str, dict]:
    """Fetch commodity prices. Returns {commodity_key: {price, change_5d_pct, change_20d_pct, unit}}."""
    try:
        raw = await _fetch()
        return raw.get("commodities") or {}
    except Exception as exception:
        logger.warning("Failed to fetch commodity prices: %s", exception)
        return {}
