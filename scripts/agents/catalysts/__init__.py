"""Catalyst Discovery Agent using PydanticAI.

Discovers regulatory and geopolitical catalysts from scraped news.
Persists to ``catalysts`` table via shared.neon.catalysts.

Module layout (post-modularisation, SWI-212):
  * ``schemas.py`` — Pydantic schemas + DetectionKeyword + CatalystType
    Literal + DB-mirrored types (re-exported CatalystFactor, CatalystDriver).
  * ``dedup.py`` — _find_duplicate_catalyst + _resolve_supporting_ids.
  * ``audit.py`` — _record_catalyst_audit (catalyst_rejections insert).
  * ``persist.py`` — _persist_discoveries (writes to catalysts table).
  * ``context.py`` — agent factory + active-catalyst formatter + discover_*.
  * ``__init__.py`` — re-exports the public surface.
"""

from __future__ import annotations

# Re-exported for tests + downstream imports — patches target this namespace.
from shared.neon.catalysts import (
    complete_catalyst,
    get_active_catalysts_db,
    link_catalyst_articles,
    update_catalyst_field,
    upsert_catalyst,
)

from .audit import _record_catalyst_audit
from .context import (
    _create_catalyst_agent,
    _format_active_catalysts_context,
    discover_catalysts_with_agent,
)
from .dedup import _find_duplicate_catalyst, _resolve_supporting_ids
from .persist import _persist_discoveries
from .schemas import (
    _CONFIDENCE_RANKS,
    CatalystAddition,
    CatalystCompletion,
    CatalystDiscovery,
    CatalystDriver,
    CatalystFactor,
    CatalystReason,
    CatalystType,
    CatalystUpdate,
    DetectionKeyword,
    _confidence_rank,
)

__all__ = [
    "CatalystAddition",
    "CatalystCompletion",
    "CatalystDiscovery",
    "CatalystDriver",
    "CatalystFactor",
    "CatalystReason",
    "CatalystType",
    "CatalystUpdate",
    "DetectionKeyword",
    "_CONFIDENCE_RANKS",
    "_confidence_rank",
    "_create_catalyst_agent",
    "_find_duplicate_catalyst",
    "_format_active_catalysts_context",
    "_persist_discoveries",
    "_record_catalyst_audit",
    "_resolve_supporting_ids",
    "complete_catalyst",
    "discover_catalysts_with_agent",
    "get_active_catalysts_db",
    "link_catalyst_articles",
    "update_catalyst_field",
    "upsert_catalyst",
]
