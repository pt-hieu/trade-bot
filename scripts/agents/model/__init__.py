"""OpenRouter model configuration for PydanticAI.

Routes through OpenRouter for automatic failover. Production models are
per-agent in YAML configs (scripts/agents/configs/), resolved at runtime
by resolve_model().

Module layout (post-modularisation, SWI-212):
  * ``wrappers.py`` — HopTimingModel + RetryModel + per-hop wall constants.
  * ``resolvers.py`` — provider cache + model resolution + health check.
    Single place where ``OpenRouterModel`` is constructed (per
    ``check_openrouter_model_construction`` pre-commit hook).
  * ``__init__.py`` — re-exports the public surface.

Singleton invariant (tests/unit/test_model_singletons.py): the
``_provider_cache`` dict lives at module scope in ``resolvers.py`` and is
reachable via ``agents.model.resolvers._provider_cache``. Importing this
package and binding ``from .resolvers import _provider_cache`` MUST
return the same object so cached httpx clients are not duplicated.
"""

from __future__ import annotations

from .resolvers import (
    _DRY_RUN_LOGGED,
    _FALLBACK_MODEL,
    _FALLBACK_MODEL_CANARY,
    _HEALTH_TTL_SECONDS,
    _build_inverted_fallback,
    _effective_fallback_model_id,
    _get_provider,
    _get_test_model,
    _get_tier,
    _health_checked_at,
    _log_tier_once,
    _logged_tier,
    _primary_healthy,
    _provider_cache,
    check_primary_model_health,
    is_dry_run,
    resolve_fallback_model,
    resolve_model,
    resolve_model_with_fallback,
)
from .wrappers import (
    ADVOCATE_PHASE_WALL_S,
    FALLBACK_HOP_WALL_S,
    OUTER_DISABLE_FALLBACK_WALL_S,
    OUTER_FALLBACK_STACK_WALL_S,
    OUTER_WALL_HEADROOM_S,
    PHASE_HEADROOM_S,
    PRIMARY_HOP_WALL_S,
    RETRY_MAX_PRIMARY,
    HopTimeout,
    HopTimingModel,
    RetryModel,
    _default_jitter_delay,
    _first_hop_timeout,
    _provider_slug_from_model_id,
    await_with_hop_unwrap,
    downstream_provider_from_timeout,
    emit_model_hop_retry_span,
    emit_model_hop_timing_span,
    provider_slug_from_timeout,
)

__all__ = [
    "ADVOCATE_PHASE_WALL_S",
    "FALLBACK_HOP_WALL_S",
    "HopTimeout",
    "HopTimingModel",
    "OUTER_DISABLE_FALLBACK_WALL_S",
    "OUTER_FALLBACK_STACK_WALL_S",
    "OUTER_WALL_HEADROOM_S",
    "PHASE_HEADROOM_S",
    "PRIMARY_HOP_WALL_S",
    "RETRY_MAX_PRIMARY",
    "RetryModel",
    "_DRY_RUN_LOGGED",
    "_FALLBACK_MODEL",
    "_FALLBACK_MODEL_CANARY",
    "_HEALTH_TTL_SECONDS",
    "_build_inverted_fallback",
    "_default_jitter_delay",
    "_effective_fallback_model_id",
    "_first_hop_timeout",
    "_get_provider",
    "_get_test_model",
    "_get_tier",
    "_health_checked_at",
    "_log_tier_once",
    "_logged_tier",
    "_primary_healthy",
    "_provider_cache",
    "_provider_slug_from_model_id",
    "await_with_hop_unwrap",
    "check_primary_model_health",
    "downstream_provider_from_timeout",
    "emit_model_hop_retry_span",
    "emit_model_hop_timing_span",
    "is_dry_run",
    "provider_slug_from_timeout",
    "resolve_fallback_model",
    "resolve_model",
    "resolve_model_with_fallback",
]
