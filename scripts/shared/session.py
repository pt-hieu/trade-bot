"""
OpenRouter session tracking — groups all LLM calls in a pipeline run.

Usage:
    from shared.session import init_session, get_extra_body

    # Call once at pipeline start (after configure_observability)
    init_session("morning")

    # Read in agent_factory or call_llm — returns None if not initialized
    extra_body = get_extra_body(agent_name="market_level")
"""

import logging
import os
from uuid import uuid4

logger = logging.getLogger(__name__)

# Module-level state — set once per process via init_session()
_session_id: str | None = None
_pipeline_name: str | None = None
_environment: str | None = None
_warned_missing_init: bool = False

# Populated mid-run by the silent-hang alerter; merges with the static
# ignore list in get_extra_body so OpenRouter stops routing the rest of
# the session through providers that degraded during this run. Cleared
# by reset_session() for tests.
_dynamic_provider_excludes: set[str] = set()

# OpenRouter serving-upstream slugs that chronically under-perform,
# independent of the fleet model. Same namespace as _dynamic_provider_excludes
# (downstream serving-upstream names), so the merge in get_extra_body is
# semantically uniform — both feed provider.ignore.
# - siliconflow: ~52 tps vs faster upstreams on the same model; implicated
#   in the 2026-04-21 silent-hang cluster. Verified slug via
#   https://openrouter.ai/provider/siliconflow.
# - together: SWI-126 investigation (2026-04-29) measured Together serving
#   the fleet model at 5–17 tok/s effective vs StreamLake/Friendli's
#   70–90 tok/s on the same agents — drove nearly all sector_*/positions_*
#   slow-tail calls that tripped the per-hop wall. Verified via
#   /api/v1/generation provider_name across 37 hang-trace generations.
# Both are upstream-throughput facts, not model-specific — they survive
# fleet model swaps. Do not delete on a model change.
_STATIC_PROVIDER_EXCLUDES: tuple[str, ...] = ("siliconflow", "together")


def add_provider_exclusion(provider_slug: str) -> None:
    """Add an OpenRouter upstream backend slug to the per-session ignore list.

    Subsequent `get_extra_body` calls will merge the slug into the
    `provider.ignore` array — OpenRouter then avoids routing through that
    backend for the remainder of the session. Idempotent.

    Called from `maybe_emit_silent_hang_alert` when a provider-class hang
    cluster (>=3 distinct agents) is detected mid-run.
    """
    if provider_slug:
        _dynamic_provider_excludes.add(provider_slug.lower())


def get_dynamic_provider_excludes() -> frozenset[str]:
    """Return the current dynamic exclusion set (test introspection)."""
    return frozenset(_dynamic_provider_excludes)


def init_session(pipeline_name: str) -> str:
    """Initialize session for a pipeline run.

    Generates a unique session_id and stores it in module state.
    All subsequent get_extra_body() calls return this session's metadata.

    Args:
        pipeline_name: Short identifier (morning, midday, retro, longterm, etc.)

    Returns:
        The generated session_id for logging.
    """
    global _session_id, _pipeline_name, _environment  # noqa: PLW0603

    from shared.config import get_scan_date

    scan_date = get_scan_date()
    suffix = uuid4().hex[:6]
    _session_id = f"{pipeline_name}_{scan_date}_{suffix}"
    _pipeline_name = pipeline_name
    _environment = os.environ.get("LOGFIRE_ENVIRONMENT", "development")

    logger.info("OpenRouter session: %s (env=%s)", _session_id, _environment)
    return _session_id


def get_session_id() -> str | None:
    """Return current session ID, or None if not initialized."""
    return _session_id


def get_extra_body(agent_name: str | None = None) -> dict | None:
    """Return extra_body dict for OpenRouter request injection.

    Returns None if init_session() was not called (zero impact).
    Logs a warning once in production when called before init.

    Args:
        agent_name: Agent key or caller identifier for trace metadata.
    """
    global _warned_missing_init  # noqa: PLW0603

    if _session_id is None:
        if not _warned_missing_init:
            _warned_missing_init = True
            logger.warning(
                "get_extra_body() called before init_session() — session tracking disabled"
            )
        return None

    trace: dict = {
        "trace_id": _session_id,
        "trace_name": _pipeline_name,
        "environment": _environment,
    }
    if agent_name:
        trace["generation_name"] = agent_name

    # Merge static (chronic offenders) + dynamic (mid-session excludes
    # populated by the silent-hang alert). `allow_fallbacks: true` keeps
    # OpenRouter routing to any other healthy backend. `sort: throughput`
    # asks OpenRouter to rank the whole eligible upstream set by speed —
    # SWI-126 showed identical-model upstreams differing 5–15× in effective
    # tok/s, so latency-sort is the second line of defence behind the static
    # exclude list and the primary proactive guard against the silent
    # first-byte/mid-stream hang (SWI-369/375/378). `require_parameters: true`
    # routes only to upstreams that support the params we send, which also
    # removes the news_relevance/article_sentiment tool_choice 404 storm
    # (SWI-376). Canonical routing strategy per [DEC] — do NOT re-pin to a
    # single upstream (the c5d69301 order:["chutes"]/quantizations:["fp8"]
    # pin caused every model to hang behind one slow/cold upstream).
    combined = sorted({*_STATIC_PROVIDER_EXCLUDES, *_dynamic_provider_excludes})
    return {
        "session_id": _session_id,
        "trace": trace,
        "provider": {
            "sort": "throughput",
            "ignore": combined,
            "allow_fallbacks": True,
            "require_parameters": True,
        },
    }


def reset_session() -> None:
    """Reset session state. Used in tests only."""
    global _session_id, _pipeline_name, _environment, _warned_missing_init  # noqa: PLW0603
    _session_id = None
    _pipeline_name = None
    _environment = None
    _warned_missing_init = False
    _dynamic_provider_excludes.clear()
