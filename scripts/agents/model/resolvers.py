"""Provider cache + model resolution + health check.

This module is the single place where ``OpenRouterModel`` is constructed,
matching the ``check_openrouter_model_construction`` pre-commit hook
allowlist. Bare construction anywhere else bypasses HopTimingModel +
RetryModel (silent-hang guards).
"""

from __future__ import annotations

import logging
import os
import time

import httpx
from openai import AsyncOpenAI
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from shared.config import CHEAP_MODEL, LLM_MODEL
from shared.env import is_dry_run

from .wrappers import HopTimingModel, RetryModel

logger = logging.getLogger(__name__)

# CHEAP_MODEL + LLM_MODEL (the fleet primary) live in shared.config — the
# single Python SSOT. Only the fleet-level fallback model, which has no
# per-agent YAML home, is defined here.
_FALLBACK_MODEL = "minimax/minimax-m2.7"

# Opt-in per-agent canary (None = default fleet). Must never auto-promote.
_FALLBACK_MODEL_CANARY: str | None = os.environ.get("SWINGY_FALLBACK_MODEL")

_DRY_RUN_LOGGED = False
_logged_tier = False

# Health check state — cached with TTL
_primary_healthy: bool | None = None
_health_checked_at: float = 0.0
_HEALTH_TTL_SECONDS = 300  # 5 min — re-check after TTL expires


def _get_test_model():
    """Return TestModel and log once."""
    global _DRY_RUN_LOGGED
    from pydantic_ai.models.test import TestModel

    if not _DRY_RUN_LOGGED:
        print("  [DRY RUN] Using TestModel for all PydanticAI agents (no LLM API calls)")
        _DRY_RUN_LOGGED = True
    return TestModel()


def _get_tier() -> str:
    return os.environ.get("SWINGY_MODEL_TIER", "production")


def _log_tier_once() -> None:
    global _logged_tier
    if not _logged_tier:
        if _get_tier() == "cheap":
            print(f"  [LLM] Using CHEAP tier ({CHEAP_MODEL})")
        _logged_tier = True


# Cached providers — one per timeout tier, avoids 60+ leaked httpx.AsyncClient instances.
# Lives at this module's scope so wrappers/__init__/resolvers all share one dict
# (the singleton invariant test in tests/unit/test_model_singletons.py asserts this).
_provider_cache: dict[float, OpenRouterProvider] = {}


def _get_provider(timeout: float = 60.0) -> OpenRouterProvider:
    """Return a cached OpenRouterProvider for the given timeout tier.

    Default is 60s — agents with `disable_fallback=True` have no exception
    pathway to fallback, so inheriting the phase-wall-length 300s here means
    a silent provider hang (first-byte never arrives) eats the full phase
    wall before surfacing. Any agent that genuinely needs > 60s must opt in
    explicitly via `_get_provider(timeout=N)` with a comment explaining why.
    """
    if timeout in _provider_cache:
        return _provider_cache[timeout]
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable not set")

    # Build the AsyncOpenAI client ourselves so `max_retries=0` actually sticks.
    # The OpenRouterProvider constructor exposes no max_retries, so the only way
    # to disable the OpenAI SDK's default in-request double-retry (max_retries=2)
    # is to inject a pre-built client via the `openai_client` overload. Without
    # this, a stalled/timed-out hop is silently retried twice INSIDE one
    # request() call (~2xN s) before HopTimingModel's per-hop wall and
    # RetryModel/FallbackModel — which own the retry budget by design — ever see
    # it. (SWI-375/378 silent provider hang.)
    #
    # Explicit read=timeout (the per-tier hop wall), short connect/write/pool as
    # a backstop only; the non-stream request() wall is the primary catch since
    # keep-alives can defeat a socket read timeout.
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=10.0, write=10.0, pool=5.0)
    )
    # OpenRouterProvider derives attribution headers from OPENROUTER_APP_URL/
    # _TITLE in every branch, but only APPLIES them to clients IT builds — the
    # `openai_client` overload assigns the caller's client as-is and drops them.
    # Re-derive here to preserve parity with the prior http_client construction.
    # NOTE: this duplicates the SDK's env-var names; if pydantic_ai renames them
    # this copy goes stale silently — update both (deliberate one-adapter parity).
    attribution_headers: dict[str, str] = {}
    if app_url := os.environ.get("OPENROUTER_APP_URL"):
        attribution_headers["HTTP-Referer"] = app_url
    if app_title := os.environ.get("OPENROUTER_APP_TITLE"):
        attribution_headers["X-Title"] = app_title
    openai_client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        http_client=http_client,
        max_retries=0,
        default_headers=attribution_headers,
    )
    provider = OpenRouterProvider(openai_client=openai_client)
    _provider_cache[timeout] = provider
    return provider


async def check_primary_model_health() -> bool:
    """Ping primary model with minimal call. Cached with 5min TTL."""
    global _primary_healthy, _health_checked_at  # noqa: PLW0603
    now = time.monotonic()
    if _primary_healthy is not None and (now - _health_checked_at) < _HEALTH_TTL_SECONDS:
        return _primary_healthy
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": LLM_MODEL,
                    "messages": [{"role": "user", "content": "1"}],
                    "max_tokens": 1,
                },
            )
            _primary_healthy = response.status_code == 200
    except Exception:
        _primary_healthy = False
    _health_checked_at = now
    if not _primary_healthy:
        print(f"  [HEALTH CHECK] {LLM_MODEL} UNHEALTHY — using {_FALLBACK_MODEL}")
    return _primary_healthy


def _effective_fallback_model_id() -> str:
    return _FALLBACK_MODEL_CANARY or _FALLBACK_MODEL


def resolve_fallback_model() -> OpenRouterModel:
    """Return fallback model (honours SWINGY_FALLBACK_MODEL canary)."""
    return OpenRouterModel(_effective_fallback_model_id(), provider=_get_provider())


_inverted_fallback_logged = False


def _build_inverted_fallback():
    """Build FallbackModel with primary/fallback swapped."""
    from pydantic_ai.models.fallback import FallbackModel

    global _inverted_fallback_logged  # noqa: PLW0603
    if not _inverted_fallback_logged:
        logger.info(
            "Agent uses %s as primary — using %s as fallback (inverted)",
            _FALLBACK_MODEL,
            LLM_MODEL,
        )
        _inverted_fallback_logged = True
    return FallbackModel(
        HopTimingModel(
            OpenRouterModel(_FALLBACK_MODEL, provider=_get_provider(timeout=60.0)),
            hop="primary",
            agent_key="inverted_fallback",
        ),
        HopTimingModel(
            OpenRouterModel(LLM_MODEL, provider=_get_provider()),
            hop="fallback",
            agent_key="inverted_fallback",
        ),
    )


def resolve_model_with_fallback(config):
    """Resolve model wrapped with automatic fallback on API errors.

    See module docstring for the full priority chain.
    """
    from pydantic_ai.models.fallback import FallbackModel

    from shared.errors import ProviderUnavailable

    if is_dry_run() or _get_tier() == "cheap":
        return resolve_model(config)

    disable_fallback = bool(getattr(config, "disable_fallback", False))

    if _primary_healthy is False:
        if disable_fallback:
            raise ProviderUnavailable(
                f"{getattr(config, 'agent_key', 'unknown')}: primary "
                f"{LLM_MODEL} unhealthy, fallback disabled by config"
            )
        if config.model_id == _FALLBACK_MODEL:
            return _build_inverted_fallback()
        return resolve_fallback_model()

    agent_key = getattr(config, "agent_key", "unknown")
    if disable_fallback:
        return RetryModel(
            HopTimingModel(
                OpenRouterModel(config.model_id, provider=_get_provider()),
                hop="primary",
                agent_key=agent_key,
            ),
        )

    if config.model_id == _FALLBACK_MODEL:
        return _build_inverted_fallback()
    primary = RetryModel(
        HopTimingModel(
            OpenRouterModel(config.model_id, provider=_get_provider(timeout=60.0)),
            hop="primary",
            agent_key=agent_key,
        ),
    )
    fallback = RetryModel(
        HopTimingModel(
            resolve_fallback_model(),
            hop="fallback",
            agent_key=agent_key,
        ),
    )
    return FallbackModel(primary, fallback)


def resolve_model(config) -> OpenRouterModel:
    """Resolve model from AgentConfig with priority chain.

    Priority:
    0. SWINGY_DRY_RUN=true → TestModel
    1. SWINGY_MODEL_TIER=cheap → Qwen 2.5 7B
    2. EVAL_MODEL_OVERRIDE → eval model override
    3. config.model_id → per-agent model from YAML
    4. No model_id → raises ValueError
    """
    if is_dry_run():
        return _get_test_model()  # type: ignore[return-value]

    _log_tier_once()

    if _get_tier() == "cheap":
        return OpenRouterModel(CHEAP_MODEL, provider=_get_provider())

    eval_override = os.environ.get("EVAL_MODEL_OVERRIDE")
    if eval_override:
        return OpenRouterModel(eval_override, provider=_get_provider())

    if config.model_id:
        return OpenRouterModel(config.model_id, provider=_get_provider())

    agent_key = getattr(config, "agent_key", "unknown")
    raise ValueError(
        f"Agent '{agent_key}' has no model_id configured. "
        f"Set model_id in scripts/agents/configs/{agent_key}.yaml"
    )
