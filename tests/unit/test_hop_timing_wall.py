"""Regression: HopTimingModel enforces a per-hop wall via asyncio.wait_for.

Before 2026-04-22, slow-streaming primaries (sector_technical,
sector_enrichment) kept httpx read-timeout from firing because OpenRouter
emitted keepalives / slow chunks. FallbackModel rolls over only on
exceptions, so the outer wall (180-240s) fired instead of the provider
timeout, surfacing as `silent_provider_hang` spans.

Now HopTimingModel wraps inner `super().request(...)` in
`asyncio.wait_for(_hop_wall_s)`. On timeout it emits
`model_hop_timing.outcome=timeout` and re-raises, letting FallbackModel
roll over to the next hop. Walls are generous (180/120s) because MiniMax
fallback is schema-broken for nested outputs, so failing fast into the
fallback usually still fails — a retry against the primary is far more
likely to succeed.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from pydantic_ai.models import Model


class _StubWrapped(Model):
    """Minimal wrapped model that takes N seconds to respond."""

    def __init__(self, delay_s: float, model_name_str: str = "test/provider-a"):
        self._delay_s = delay_s
        self._model_name_str = model_name_str
        self.call_count = 0

    async def request(self, messages, model_settings, model_request_parameters):
        self.call_count += 1
        await asyncio.sleep(self._delay_s)
        return {"ok": True}

    @property
    def model_name(self) -> str:  # type: ignore[override]
        return self._model_name_str

    @property
    def system(self) -> str:  # type: ignore[override]
        return "stub"


@pytest.mark.asyncio
async def test_hop_wall_fires_on_slow_primary():
    """Slow wrapped.request (2s) under a 0.1s wall raises TimeoutError."""
    from agents.model import HopTimingModel

    wrapped = _StubWrapped(delay_s=2.0)
    wall = HopTimingModel(
        wrapped,
        hop="primary",
        agent_key="test_agent",
        hop_wall_s=0.1,
    )
    emitted: list[dict[str, Any]] = []

    def _record(**kwargs):
        emitted.append(kwargs)

    with (
        patch("agents.model.wrappers.emit_model_hop_timing_span", side_effect=_record),
        pytest.raises(asyncio.TimeoutError),
    ):
        await wall.request(messages=[], model_settings={}, model_request_parameters={})

    # The wrapped request was invoked once and cancelled
    assert wrapped.call_count == 1
    # Exactly one span emitted with outcome=timeout
    assert len(emitted) == 1
    assert emitted[0]["outcome"] == "timeout"
    assert emitted[0]["hop"] == "primary"
    assert emitted[0]["agent"] == "test_agent"
    # Provider slug derived from the model_id prefix (test/provider-a → test)
    assert emitted[0]["provider"] == "test"


@pytest.mark.asyncio
async def test_hop_wall_lets_fast_primary_through():
    """Fast wrapped.request completes inside the wall without TimeoutError."""
    from agents.model import HopTimingModel

    wrapped = _StubWrapped(delay_s=0.05)
    wall = HopTimingModel(
        wrapped,
        hop="primary",
        agent_key="test_agent",
        hop_wall_s=1.0,
    )
    emitted: list[dict[str, Any]] = []

    def _record(**kwargs):
        emitted.append(kwargs)

    with patch("agents.model.wrappers.emit_model_hop_timing_span", side_effect=_record):
        result = await wall.request(messages=[], model_settings={}, model_request_parameters={})

    assert result == {"ok": True}
    assert len(emitted) == 1
    assert emitted[0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_hop_wall_default_primary_75s():
    """Primary hop uses PRIMARY_HOP_WALL_S=75 by default (latency-triage policy, SWI-318)."""
    from agents.model import PRIMARY_HOP_WALL_S, HopTimingModel

    wrapped = _StubWrapped(delay_s=0.0)
    wall = HopTimingModel(wrapped, hop="primary", agent_key="test")
    assert wall._hop_wall_s == PRIMARY_HOP_WALL_S == 75.0


def test_outer_wall_invariants_hold_at_primary_75s():
    """At PRIMARY_HOP_WALL_S=75 the module-load invariants in wrappers.py:62-71
    still satisfy OUTER_FALLBACK_STACK_WALL_S > PRIMARY + FALLBACK and
    OUTER_DISABLE_FALLBACK_WALL_S > PRIMARY. Importing the module exercises
    the raise-guards at load time; this test then re-asserts the relationship
    so a future PRIMARY cut that breaks them fails loudly."""
    import agents.model.wrappers as w

    assert w.PRIMARY_HOP_WALL_S == 75.0
    assert w.OUTER_FALLBACK_STACK_WALL_S > w.PRIMARY_HOP_WALL_S + w.FALLBACK_HOP_WALL_S
    assert w.OUTER_DISABLE_FALLBACK_WALL_S > w.PRIMARY_HOP_WALL_S


@pytest.mark.asyncio
async def test_hop_wall_default_fallback_120s():
    """Fallback hop uses FALLBACK_HOP_WALL_S=120 by default."""
    from agents.model import FALLBACK_HOP_WALL_S, HopTimingModel

    wrapped = _StubWrapped(delay_s=0.0)
    wall = HopTimingModel(wrapped, hop="fallback", agent_key="test")
    assert wall._hop_wall_s == FALLBACK_HOP_WALL_S == 120.0


def test_provider_slug_extraction():
    from agents.model import _provider_slug_from_model_id

    assert _provider_slug_from_model_id("moonshotai/Kimi-K2.5") == "moonshotai"
    assert _provider_slug_from_model_id("z-ai/glm-5") == "z-ai"
    assert _provider_slug_from_model_id("minimax/minimax-m2.7") == "minimax"
    # Fallback: no slash — treat whole string as slug, lowercased
    assert _provider_slug_from_model_id("Qwen2.5-7B") == "qwen2.5-7b"


# ─────────────────────────────────────────────────────────────────────────────
# resolve_model_with_fallback wiring — detailed RetryModel semantics live in
# test_retry_model.py; this file owns the per-hop-wall regression tests only.
# ─────────────────────────────────────────────────────────────────────────────


def test_disable_fallback_returns_retry_wrapped_instance():
    """resolve_model_with_fallback(disable_fallback=True) wraps in RetryModel."""
    import os
    from dataclasses import dataclass

    from agents.model import HopTimingModel, RetryModel

    old_dry = os.environ.pop("SWINGY_DRY_RUN", None)
    old_tier = os.environ.pop("SWINGY_MODEL_TIER", None)
    os.environ.setdefault("OPENROUTER_API_KEY", "dummy-for-test")

    try:

        @dataclass
        class _Cfg:
            model_id: str = "moonshotai/Kimi-K2.5"
            agent_key: str = "test_disable_fallback"
            disable_fallback: bool = True

        from agents import model as model_mod

        saved_health = model_mod._primary_healthy
        model_mod._primary_healthy = True
        try:
            model = model_mod.resolve_model_with_fallback(_Cfg())
        finally:
            model_mod._primary_healthy = saved_health

        assert isinstance(model, RetryModel)
        assert isinstance(model.wrapped, HopTimingModel)
    finally:
        if old_dry is not None:
            os.environ["SWINGY_DRY_RUN"] = old_dry
        if old_tier is not None:
            os.environ["SWINGY_MODEL_TIER"] = old_tier
