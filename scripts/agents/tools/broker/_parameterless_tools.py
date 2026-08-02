"""Registry-derived ``PARAMETERLESS_TOOLS`` set.

A tool is "parameterless" when its JSON Schema declares an empty
``properties`` dict — agents must invoke these with ``args={}``.
"""

from __future__ import annotations

from functools import lru_cache

from .registry import TOOL_CATALOG


@lru_cache(maxsize=1)
def get_parameterless_tools() -> frozenset[str]:
    return frozenset(
        name for name, td in TOOL_CATALOG.items() if not (td.parameters.get("properties") or {})
    )
