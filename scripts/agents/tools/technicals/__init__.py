"""Technical analysis tools for fetching ticker data.

Uses Neon database for daily scan data, with fallback to real-time vnstock fetch.

Module layout (post-modularisation, SWI-212; touches SWI-42 batch seam):
  * ``prose.py`` — _format_technicals_prose, _check_staleness,
    is_structural_uptrend.
  * ``setup_calc.py`` — compute_setup_from_levels + helpers + constants.
  * ``fetch_async.py`` — async ticker fetchers (single + batch + realtime)
    + tool_get_* + compute_trade_setup_async (batch path is the SWI-42 seam).
  * ``sync_compat.py`` — get_ticker_data sync wrapper for CLI scripts.
  * ``__init__.py`` — re-exports the public surface.
"""

from __future__ import annotations

from .fetch_async import (
    _REALTIME_CACHE,
    _extract_trade_setup,
    compute_batch_trade_setup_async,
    compute_trade_setup_async,
    fetch_technicals_realtime_async,
    get_batch_ticker_data_async,
    get_ticker_data_async,
    tool_get_technicals,
    tool_get_technicals_realtime,
)
from .prose import (
    _check_staleness,
    _format_technicals_prose,
    is_structural_uptrend,
)
from .setup_calc import (
    _AGGRESSIVE_RR_STRETCH_FACTOR,
    _MARKET_ENTRY_GAP_PCT,
    _STOP_BUFFER_PCT,
    ATR_STOP_MULT,
    REGIME_TARGET_MULT,
    _build_single_setup,
    _enrich_with_setup_and_prose,
    _stretch_rr_from_target,
    compute_setup_from_levels,
)
from .sync_compat import get_ticker_data

__all__ = [
    "ATR_STOP_MULT",
    "REGIME_TARGET_MULT",
    "_AGGRESSIVE_RR_STRETCH_FACTOR",
    "_MARKET_ENTRY_GAP_PCT",
    "_REALTIME_CACHE",
    "_STOP_BUFFER_PCT",
    "_build_single_setup",
    "_check_staleness",
    "_enrich_with_setup_and_prose",
    "_extract_trade_setup",
    "_format_technicals_prose",
    "_stretch_rr_from_target",
    "compute_batch_trade_setup_async",
    "compute_setup_from_levels",
    "compute_trade_setup_async",
    "fetch_technicals_realtime_async",
    "get_batch_ticker_data_async",
    "get_ticker_data",
    "get_ticker_data_async",
    "is_structural_uptrend",
    "tool_get_technicals",
    "tool_get_technicals_realtime",
]
