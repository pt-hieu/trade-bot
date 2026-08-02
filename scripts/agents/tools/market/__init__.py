"""Market-level tools for VN-Index data, sector rotation, and regime detection.

Module layout (post-modularisation, SWI-212):
  * ``formatters.py`` — _format_*_prose helpers (regime/rotation/macro/history).
  * ``async_tools.py`` — get_*_async + tool_get_* (PydanticAI agent surface).
  * ``sync_tools.py`` — sync wrappers using shared.async_compat.run_async
    for CLI script compatibility.
  * ``__init__.py`` — re-exports public API.
"""

from __future__ import annotations

from .async_tools import (
    get_macro_history_async,
    get_macro_metrics_async,
    get_market_regime_async,
    get_regime_history_async,
    get_sector_rotation_async,
    tool_get_macro,
    tool_get_macro_history,
    tool_get_regime,
    tool_get_regime_history,
    tool_get_rotation,
)
from .formatters import (
    _format_macro_history_prose,
    _format_macro_prose,
    _format_regime_history_prose,
    _format_regime_prose,
    _format_rotation_prose,
)
from .sync_tools import (
    get_macro_history,
    get_macro_metrics,
    get_market_regime,
    get_regime_history,
    get_sector_rotation,
    get_sector_technicals,
    get_vnindex_technicals,
)

__all__ = [
    "_format_macro_history_prose",
    "_format_macro_prose",
    "_format_regime_history_prose",
    "_format_regime_prose",
    "_format_rotation_prose",
    "get_macro_history",
    "get_macro_history_async",
    "get_macro_metrics",
    "get_macro_metrics_async",
    "get_market_regime",
    "get_market_regime_async",
    "get_regime_history",
    "get_regime_history_async",
    "get_sector_rotation",
    "get_sector_rotation_async",
    "get_sector_technicals",
    "get_vnindex_technicals",
    "tool_get_macro",
    "tool_get_macro_history",
    "tool_get_regime",
    "tool_get_regime_history",
    "tool_get_rotation",
]
