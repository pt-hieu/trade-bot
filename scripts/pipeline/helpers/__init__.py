"""Pipeline helper functions for pre/post-processing between phases.

Module layout (post-modularisation, SWI-212 FIX 5: split by TYPE,
not 7-way by topic):
  * ``rules.py`` — pure sync rules (regimes, oil patch, workflow_classifier).
  * ``io.py`` — async DB I/O (load_db_context, persist_phase1, post_process_phase1,
    fetch_catalyst_bundle).
  * ``derive.py`` — async orchestrators (derive_intermediates, get_market_level,
    load_sector_rotation, resolve_trading_mode, compose_gate_from_state).
  * ``__init__.py`` — re-exports the public surface so consumers (live pipeline,
    resume path, sector_rotation agent, tests) keep their existing imports.
"""

from __future__ import annotations

from .derive import (
    compose_gate_from_state,
    derive_intermediates,
    get_market_level,
    load_sector_rotation,
    resolve_trading_mode,
)
from .io import (
    _safe_catalyst_bundle,
    load_db_context,
    persist_phase1,
    post_process_phase1,
)
from .rules import (
    ProducerLeakError,
    determine_adaptive_workflow,
    extract_risk_regime,
    patch_oil_from_commodities,
    reconcile_regimes,
)

__all__ = [
    "ProducerLeakError",
    "_safe_catalyst_bundle",
    "compose_gate_from_state",
    "derive_intermediates",
    "determine_adaptive_workflow",
    "extract_risk_regime",
    "get_market_level",
    "load_db_context",
    "load_sector_rotation",
    "patch_oil_from_commodities",
    "persist_phase1",
    "post_process_phase1",
    "reconcile_regimes",
    "resolve_trading_mode",
]
