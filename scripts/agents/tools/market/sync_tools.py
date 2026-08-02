"""Sync wrappers for CLI scripts (backwards compatibility)."""

from __future__ import annotations

import logging
from datetime import date
from typing import cast

from shared.async_compat import run_async as _run_async
from shared.neon import MacroHistoryEntry, RegimeHistoryEntry

logger = logging.getLogger(__name__)


def get_vnindex_technicals(scan_date: date | None = None) -> dict:
    """Get VN-Index technical data."""
    from shared.api.technicals import get_ticker_technicals

    try:
        result = cast(dict, _run_async(get_ticker_technicals("VNINDEX")))
        if "error" not in result:
            return {
                "close": result.get("close"),
                "rsi": result.get("rsi"),
                "ma20": result.get("ma20"),
                "ma50": result.get("ma50"),
                "price_vs_ma20": result.get("price_vs_ma20"),
                "price_vs_ma50": result.get("price_vs_ma50"),
                "levels": result.get("levels"),
            }
        return result
    except Exception as e:
        return {"error": f"Failed to get VN-Index data: {e}"}


def get_sector_rotation(scan_date: date | None = None) -> dict:
    """Get sector rotation analysis."""
    from shared.neon import get_sector_rotation as _get_sector_rotation

    if scan_date is None:
        scan_date = date.today()

    try:
        return _run_async(_get_sector_rotation(scan_date))
    except Exception as e:
        return {"error": f"Failed to get sector rotation: {e}"}


def get_market_regime(scan_date: date | None = None) -> dict:
    """Get market regime classification."""
    from shared.neon import get_market_regime as _get_market_regime

    if scan_date is None:
        scan_date = date.today()

    try:
        return _run_async(_get_market_regime(scan_date))
    except Exception as e:
        return {"error": f"Failed to get market regime: {e}"}


def get_regime_history(days: int = 5) -> list[RegimeHistoryEntry]:
    """Get regime history for the last N days."""
    from shared.neon import get_regime_history as _get_regime_history

    try:
        return _run_async(_get_regime_history(days))
    except Exception as e:
        logger.warning("Failed to get regime history: %s", e)
        return []


def get_sector_technicals(scan_date: date | None = None) -> dict:
    """Get technicals for all stocks grouped by sector."""
    from shared.api.technicals import get_technicals
    from shared.neon import get_swing_watchlist

    try:
        watchlist = _run_async(get_swing_watchlist())
        tickers = [t for sector_tickers in watchlist.values() for t in sector_tickers]
        technicals = _run_async(get_technicals(tickers)) if tickers else {}
        if "error" in technicals:
            return technicals

        sector_map = {
            "TCB": "banking",
            "CTG": "banking",
            "VCB": "banking",
            "TPB": "banking",
            "BID": "banking",
            "VHM": "real_estate",
            "NLG": "real_estate",
            "KBC": "real_estate",
            "BCM": "real_estate",
            "IDC": "real_estate",
            "KDH": "real_estate",
            "DXS": "infrastructure",
            "FPT": "technology",
            "MWG": "consumer",
            "SSI": "securities",
            "VIX": "technology",
            "GAS": "state_owned",
            "POW": "state_owned",
            "PLX": "state_owned",
            "GVR": "state_owned",
            "HVN": "state_owned",
            "BVH": "state_owned",
            "VIC": "consumer",
            "MSN": "consumer",
            "SAB": "consumer",
            "VNM": "consumer",
            "PVT": "infrastructure",
            "PVI": "infrastructure",
            "SZC": "infrastructure",
            "HPG": "infrastructure",
        }

        sectors = {}
        for ticker, data in technicals.items():
            if ticker == "VNINDEX":
                continue
            sector = sector_map.get(ticker, "other")
            if sector not in sectors:
                sectors[sector] = []
            sectors[sector].append(
                {
                    "ticker": ticker,
                    "rsi": data.get("rsi"),
                    "ma20": data.get("ma20"),
                    "price_vs_ma20": data.get("price_vs_ma20"),
                }
            )

        return sectors
    except Exception as e:
        return {"error": f"Failed to get sector technicals: {e}"}


def get_macro_metrics(scan_date: date | None = None) -> dict:
    """Get global macro metrics (DXY, VIX, USD/VND, risk regime)."""
    from shared.neon import get_macro_metrics as _get_macro_metrics

    if scan_date is None:
        scan_date = date.today()

    try:
        return _run_async(_get_macro_metrics(scan_date))
    except Exception as e:
        return {"error": f"Failed to get macro metrics: {e}"}


def get_macro_history(days: int = 5) -> list[MacroHistoryEntry]:
    """Get macro regime history for the last N days."""
    from shared.neon import get_macro_history as _get_macro_history

    try:
        return _run_async(_get_macro_history(days))
    except Exception as e:
        logger.warning("Failed to get macro history: %s", e)
        return []
