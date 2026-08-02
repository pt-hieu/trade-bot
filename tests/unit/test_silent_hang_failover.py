"""SWI-306 failover-stack structural tests."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from pydantic_ai.models import Model

from agents.model.wrappers import (
    FALLBACK_HOP_WALL_S,
    OUTER_DISABLE_FALLBACK_WALL_S,
    OUTER_FALLBACK_STACK_WALL_S,
    OUTER_WALL_HEADROOM_S,
    PRIMARY_HOP_WALL_S,
    RETRY_MAX_PRIMARY,
    HopTimeout,
    HopTimingModel,
    _first_hop_timeout,
    downstream_provider_from_timeout,
    provider_slug_from_timeout,
)


def test_outer_wall_constants_match_derivation():
    """Outer-wall constants must equal the documented derivation so a
    future edit to PRIMARY/FALLBACK/RETRY budgets propagates atomically
    instead of silently restoring the wall-equality regression."""
    expected_fallback_stack = (
        (RETRY_MAX_PRIMARY + 1) * PRIMARY_HOP_WALL_S + FALLBACK_HOP_WALL_S + OUTER_WALL_HEADROOM_S
    )
    expected_disable_fallback = (RETRY_MAX_PRIMARY + 1) * PRIMARY_HOP_WALL_S + OUTER_WALL_HEADROOM_S
    assert expected_fallback_stack == OUTER_FALLBACK_STACK_WALL_S
    assert expected_disable_fallback == OUTER_DISABLE_FALLBACK_WALL_S
    # The wall-equality regression (sector_analysts:164 == PRIMARY_HOP_WALL_S
    # = 180) must remain structurally impossible.
    assert OUTER_FALLBACK_STACK_WALL_S > PRIMARY_HOP_WALL_S + FALLBACK_HOP_WALL_S
    assert OUTER_DISABLE_FALLBACK_WALL_S > PRIMARY_HOP_WALL_S


def test_hop_timeout_is_timeout_error_subclass():
    """HopTimeout must subclass TimeoutError so existing `except TimeoutError`
    branches continue to catch it during the transition."""
    assert issubclass(HopTimeout, TimeoutError)


def test_hop_timeout_carries_provider_slug():
    """A HopTimeout must carry suspected upstream provider context so
    emit-sites can populate `emit_silent_provider_hang_span(provider=...)`."""
    exc = HopTimeout(
        "primary hop wall fired",
        provider_slug="z-ai",
        downstream_provider="z-ai-cluster-2",
    )
    assert exc.provider_slug == "z-ai"
    assert exc.downstream_provider == "z-ai-cluster-2"
    bare = HopTimeout("wall fired", provider_slug="moonshotai")
    assert bare.provider_slug == "moonshotai"
    assert bare.downstream_provider is None


def test_provider_slug_vs_downstream_provider_from_timeout():
    """`provider_slug_from_timeout` returns the model AUTHOR (for the span
    attribute, never excluded); `downstream_provider_from_timeout` returns
    the serving UPSTREAM (the only slug safe to exclude). On the common
    silent-hang shape — wall fires before any response byte — downstream is
    None, so callers exclude nothing rather than risk a fleet kill switch
    (2026-05-15 incident)."""
    identified = HopTimeout(
        "wall fired", provider_slug="moonshotai", downstream_provider="together"
    )
    assert provider_slug_from_timeout(identified) == "moonshotai"
    assert downstream_provider_from_timeout(identified) == "together"

    silent = HopTimeout("wall fired", provider_slug="moonshotai")
    assert provider_slug_from_timeout(silent) == "moonshotai"
    assert downstream_provider_from_timeout(silent) is None

    # Plain TimeoutError (outer wall, no HopTimeout to inspect) → None.
    assert provider_slug_from_timeout(TimeoutError("plain")) is None
    assert downstream_provider_from_timeout(TimeoutError("plain")) is None


def test_first_hop_timeout_unwraps_exception_group():
    """`_first_hop_timeout(eg)` recursively walks BaseExceptionGroup
    structures and returns the first HopTimeout encountered."""
    inner = HopTimeout("primary hop wall fired", provider_slug="z-ai")
    group = BaseExceptionGroup("fallback stack", [inner])
    hit = _first_hop_timeout(group)
    assert hit is inner
    # Nested group.
    nested = BaseExceptionGroup("outer", [BaseExceptionGroup("inner", [inner])])
    assert _first_hop_timeout(nested) is inner
    # No HopTimeout → None.
    other_group = BaseExceptionGroup("misc", [ValueError("nope")])
    assert _first_hop_timeout(other_group) is None
    # Bare HopTimeout passes through.
    assert _first_hop_timeout(inner) is inner


def test_phase_wall_catches_inner_reraise():
    """An outer `except HopTimeout:` (non-star) must catch a HopTimeout that
    was re-raised from inside an `except* HopTimeout as eg:` block via
    `raise _first_hop_timeout(eg) from eg`. Bare `raise` re-raises the
    BaseExceptionGroup and breaks the outer handler (Round-3 H11)."""
    inner = HopTimeout("primary hop wall fired", provider_slug="z-ai")

    def inner_layer() -> None:
        raise BaseExceptionGroup("fallback stack", [inner])

    def middle_layer() -> None:
        try:
            inner_layer()
        except* HopTimeout as eg:
            hit = _first_hop_timeout(eg)
            assert hit is not None
            raise hit from eg

    caught: HopTimeout | None = None
    try:
        middle_layer()
    except HopTimeout as e:
        caught = e
    assert caught is inner
    assert caught is not None
    assert caught.provider_slug == "z-ai"


class _HangingModel(Model):
    """Wrapped model whose request never returns — it outlives any hop wall."""

    async def request(self, messages, model_settings, model_request_parameters):
        await asyncio.sleep(30)
        raise AssertionError("unreachable — the hop wall must fire first")

    @property
    def model_name(self) -> str:  # type: ignore[override]
        return "moonshotai/kimi-k2.5"

    @property
    def system(self) -> str:  # type: ignore[override]
        return "stub"


@pytest.mark.asyncio
async def test_hop_timeout_downstream_provider_is_none_on_real_timeout():
    """A HopTimeout produced by HopTimingModel hitting its wall always carries
    `downstream_provider=None`.

    The wall fires before `request()` can read OpenRouter's `provider_details`,
    so no producer ever populates the field on a timeout path. Locks the
    SWI-369 / SWI-370 structural fact: the dynamic provider-exclusion wire is
    inert for the hop-timeout class *by construction, not by accident* —
    `_should_fail_fast` and `_populate_provider_exclusions` are deliberate
    no-ops until a future producer fills the field. The author slug stays
    populated (for the observability span) but is never excludable.
    """
    model = HopTimingModel(_HangingModel(), hop="primary", agent_key="test", hop_wall_s=0.01)

    caught: HopTimeout | None = None
    with patch("agents.model.wrappers.emit_model_hop_timing_span"):
        try:
            await model.request([], {}, {})
        except HopTimeout as exc:
            caught = exc

    assert caught is not None
    assert caught.provider_slug == "moonshotai"  # author slug — always populated
    assert caught.downstream_provider is None  # structural: never set on a timeout
