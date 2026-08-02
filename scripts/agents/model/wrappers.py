"""HopTimingModel + RetryModel — silent-hang-proofing wrappers around OpenRouterModel."""

from __future__ import annotations

import asyncio
import logging
import random
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from pydantic_ai.models.wrapper import WrapperModel

from shared.observability import emit_model_hop_retry_span, emit_model_hop_timing_span
from shared.session import get_dynamic_provider_excludes

logger = logging.getLogger(__name__)

# Per-hop wall defaults (seconds). Walls prioritize latency: 75s caps each
# primary hop so a slow-streaming provider surfaces fast enough for
# FallbackModel to roll over before the agent's outer wall fires.
# Rationale: SWI-318 — historic "generous wall to favor primary retry"
# policy retired; user trade-off (latency triage vs completion-tail
# tolerance). Worst case per agent: (RETRY_MAX_PRIMARY+1)*PRIMARY +
# FALLBACK = 345s.
# Revert/raise if model_hop_timing outcome=timeout rate > 10% over 5
# consecutive morning scans.
PRIMARY_HOP_WALL_S: float = 75.0
FALLBACK_HOP_WALL_S: float = 120.0

# Retry budget on the primary hop (must mirror `_RETRY_MAX_RETRIES` below).
# Named at module-scope so derived outer-wall constants stay in lockstep.
RETRY_MAX_PRIMARY: int = 2

# Headroom above the tightest possible failover budget — covers asyncio
# task-scheduling slack, jittered RetryModel backoff, span emission.
# SWI-306 (2026-05-16) raised 30→60 after Logfire showed 37-91% primary timeouts.
OUTER_WALL_HEADROOM_S: float = 60.0

# Outer wall for agents where FallbackModel is enabled. Must exceed the
# worst-case (RETRY_MAX_PRIMARY+1) × PRIMARY + FALLBACK budget so the
# wall-equality regression (sector_analysts:164, 2026-05-10 incident) can't
# starve the failover stack again.
OUTER_FALLBACK_STACK_WALL_S: float = (
    (RETRY_MAX_PRIMARY + 1) * PRIMARY_HOP_WALL_S + FALLBACK_HOP_WALL_S + OUTER_WALL_HEADROOM_S
)

# Outer wall for `disable_fallback: true` agents — no fallback hop, so we
# only budget for the primary's retry chain.
OUTER_DISABLE_FALLBACK_WALL_S: float = (
    RETRY_MAX_PRIMARY + 1
) * PRIMARY_HOP_WALL_S + OUTER_WALL_HEADROOM_S

# Phase-level headroom on top of an outer-wall — orchestrators that wait on
# a single agent's failover stack add this to derive their own phase wall.
PHASE_HEADROOM_S: float = 200.0

# Advocate / reviewer phase wall (single agent on the failover stack + room
# for downstream stitching).
ADVOCATE_PHASE_WALL_S: float = OUTER_FALLBACK_STACK_WALL_S + PHASE_HEADROOM_S

# Module-load invariants — guard the wall-hierarchy that lets failover run.
# Use raise instead of `assert` so `python -O` cannot strip the check.
if not OUTER_FALLBACK_STACK_WALL_S > PRIMARY_HOP_WALL_S + FALLBACK_HOP_WALL_S:
    raise RuntimeError(
        "OUTER_FALLBACK_STACK_WALL_S must exceed PRIMARY + FALLBACK to leave room "
        "for retries; otherwise the outer guard collapses the failover stack."
    )
if not OUTER_DISABLE_FALLBACK_WALL_S > PRIMARY_HOP_WALL_S:
    raise RuntimeError(
        "OUTER_DISABLE_FALLBACK_WALL_S must exceed PRIMARY_HOP_WALL_S so a "
        "single retry can fire on disable_fallback agents."
    )


class HopTimeout(TimeoutError):
    """Typed timeout raised by `HopTimingModel` when a per-hop wall fires.

    Carries the suspected upstream provider context so emit-sites can
    populate `emit_silent_provider_hang_span(provider=...)` without
    re-deriving it. Inherits from `TimeoutError` so existing
    `except TimeoutError` branches still catch it during the transition.

    Fields:
        provider_slug: OpenRouter author slug (e.g. ``"z-ai"``), derived
            from the model id at HopTimingModel construction time. Always
            populated.
        downstream_provider: Serving upstream slug from OpenRouter's
            ``provider_details`` field. Structurally ``None`` on EVERY
            hop-timeout path: a timeout means the wall fired before
            ``request()`` / ``request_stream()`` could read
            ``provider_details`` off a response, so no producer ever
            populates it on a timeout. The field — and the dynamic
            provider-exclusion wire it feeds (`_should_fail_fast`,
            `emit_silent_provider_hang_span`) — is therefore inert for
            the hop-timeout class by construction; recovery is RetryModel
            retries + FallbackModel rollover + OpenRouter re-routing. It
            is kept as ready plumbing for a future producer (header-based
            capture, or a multi-author fleet where an author slug becomes
            excludable again) — see SWI-370.
    """

    def __init__(
        self,
        message: str = "",
        *,
        provider_slug: str | None = None,
        downstream_provider: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_slug = provider_slug
        self.downstream_provider = downstream_provider


def _first_hop_timeout(eg: BaseException) -> HopTimeout | None:
    """Recursively walk a `BaseExceptionGroup` and return the first
    `HopTimeout` found, else `None`.

    `FallbackModel` wraps hop exceptions in a `FallbackExceptionGroup` (a
    `BaseExceptionGroup` subclass). An outer `except HopTimeout:` MISSES
    a wrapped HopTimeout — emit-sites MUST use `except* HopTimeout as eg:`
    and unwrap via this helper to retrieve provider context.
    """
    if isinstance(eg, HopTimeout):
        return eg
    if isinstance(eg, BaseExceptionGroup):
        for child in eg.exceptions:
            hit = _first_hop_timeout(child)
            if hit is not None:
                return hit
    return None


def provider_slug_from_timeout(exc: BaseException) -> str | None:
    """Return the model-author slug from a TimeoutError (e.g. ``"moonshotai"``).

    Emit-sites use this for the `silent_provider_hang` span's `provider`
    attribute. It identifies the *model*, not a routable upstream — it
    MUST NOT be fed to the session provider-exclusion set: when the whole
    fleet shares one author, excluding it turns the set into a fleet-wide
    kill switch (the 2026-05-15 incident). Use
    `downstream_provider_from_timeout` for exclusion.
    """
    if isinstance(exc, HopTimeout):
        return exc.provider_slug
    return None


def downstream_provider_from_timeout(exc: BaseException) -> str | None:
    """Return the OpenRouter serving-upstream slug from a TimeoutError, if known.

    This is the only slug safe to add to the session provider-exclusion
    set — excluding it makes OpenRouter route the same model through a
    healthy upstream (`provider.ignore` + `allow_fallbacks: true`).

    Returns `None` for every `HopTimeout` produced today: the per-hop
    wall always fires before OpenRouter's `provider_details` can be read,
    so `HopTimeout.downstream_provider` is structurally unpopulated on the
    timeout path (see the `HopTimeout` docstring + SWI-370). The accessor
    and its consumers are kept as ready plumbing for a future producer;
    until one exists, the dynamic provider-exclusion set never gains a
    slug from a hop timeout — and that is the intended behaviour, because
    an author-slug fallback would be a fleet-wide kill switch (2026-05-15).
    """
    if isinstance(exc, HopTimeout):
        return exc.downstream_provider
    return None


async def await_with_hop_unwrap(coro, timeout: float):
    """Await `coro` under `asyncio.wait_for(timeout)`, unwrapping any
    `HopTimeout` that `FallbackModel` has buried in a
    `FallbackExceptionGroup`. Emit-sites can then `except TimeoutError`
    (or `except HopTimeout` for a typed branch) without juggling
    `except*` syntax themselves.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except* HopTimeout as eg:
        hit = _first_hop_timeout(eg)
        if hit is not None:
            raise hit from eg
        raise


def _provider_slug_from_model_id(model_id: str) -> str:
    """Extract the OpenRouter author slug (text before the first `/`)."""
    if "/" in model_id:
        return model_id.split("/", 1)[0].lower()
    return model_id.lower()


class HopTimingModel(WrapperModel):
    """Wraps an OpenRouterModel to emit per-request timing spans AND enforce
    a per-hop wall-clock timeout.

    The wall-clock guard closes a silent-hang class of bugs where OpenRouter
    keepalives kept the httpx read-timeout from firing — FallbackModel only
    rolls over on exceptions, so a slow-streaming primary would eat the outer
    180-240s per-attempt wall before surfacing. After the wall fires, we emit
    ``outcome="timeout"`` and re-raise ``asyncio.TimeoutError`` so
    FallbackModel promotes to the next hop.
    """

    def __init__(
        self,
        wrapped,
        *,
        hop: Literal["primary", "fallback"],
        agent_key: str = "unknown",
        hop_wall_s: float | None = None,
    ):
        super().__init__(wrapped)
        self._hop: Literal["primary", "fallback"] = hop
        self._agent_key = agent_key
        self._wrapped_model_name = getattr(wrapped, "model_name", "unknown")
        self._provider_slug = _provider_slug_from_model_id(self._wrapped_model_name)
        if hop_wall_s is not None:
            self._hop_wall_s = hop_wall_s
        else:
            self._hop_wall_s = PRIMARY_HOP_WALL_S if hop == "primary" else FALLBACK_HOP_WALL_S

    def _emit(
        self,
        start: float,
        outcome: Literal["success", "error", "timeout"],
        downstream_provider: str | None = None,
    ) -> None:
        effective_span_provider = downstream_provider or self._provider_slug
        emit_model_hop_timing_span(
            agent=self._agent_key,
            model_id=self._wrapped_model_name,
            hop=self._hop,
            duration_ms=int((time.monotonic() - start) * 1000),
            outcome=outcome,
            logger=logger,
            provider=effective_span_provider,
            provider_author=self._provider_slug,
            hop_wall_s=self._hop_wall_s,
        )

    @staticmethod
    def _extract_downstream_provider(result: object) -> str | None:
        """Read OpenRouter's serving upstream slug from a ModelResponse."""
        try:
            details = getattr(result, "provider_details", None)
            if isinstance(details, dict):
                value = details.get("downstream_provider")
                if isinstance(value, str) and value:
                    return value.lower()
        except Exception:
            pass
        return None

    async def request(self, messages, model_settings, model_request_parameters):
        start = time.monotonic()
        outcome: Literal["success", "error", "timeout"] = "success"
        downstream: str | None = None
        try:
            result = await asyncio.wait_for(
                super().request(messages, model_settings, model_request_parameters),
                timeout=self._hop_wall_s,
            )
            downstream = self._extract_downstream_provider(result)
            return result
        except TimeoutError:
            outcome = "timeout"
            raise HopTimeout(
                f"hop={self._hop} wall={self._hop_wall_s}s fired",
                provider_slug=self._provider_slug,
                downstream_provider=downstream,
            ) from None
        except Exception:
            outcome = "error"
            raise
        finally:
            self._emit(start, outcome, downstream_provider=downstream)

    @asynccontextmanager
    async def request_stream(
        self,
        messages,
        model_settings,
        model_request_parameters,
        run_context=None,
    ):
        start = time.monotonic()
        outcome: Literal["success", "error", "timeout"] = "success"
        downstream: str | None = None
        try:
            stream_ctx = self.wrapped.request_stream(
                messages,
                model_settings,
                model_request_parameters,
                run_context,
            )
            response_stream = await asyncio.wait_for(
                stream_ctx.__aenter__(),
                timeout=self._hop_wall_s,
            )
            try:
                yield response_stream
                downstream = self._extract_downstream_provider(response_stream)
            except BaseException:
                exc_type, exc_val, exc_tb = sys.exc_info()
                if not await stream_ctx.__aexit__(exc_type, exc_val, exc_tb):
                    raise
            else:
                await stream_ctx.__aexit__(None, None, None)
        except TimeoutError:
            outcome = "timeout"
            raise HopTimeout(
                f"hop={self._hop} stream wall={self._hop_wall_s}s fired",
                provider_slug=self._provider_slug,
                downstream_provider=downstream,
            ) from None
        except Exception:
            outcome = "error"
            raise
        finally:
            self._emit(start, outcome, downstream_provider=downstream)


# Retry budget lives inside the wrapper (not inside FallbackModel) so both
# disable_fallback and fallback-enabled agents get identical retry semantics
# on the primary hop.
_RETRY_JITTER_MIN_S: float = 2.0
_RETRY_JITTER_MAX_S: float = 8.0
_RETRY_MAX_RETRIES: int = 2


def _default_jitter_delay() -> float:
    return random.uniform(_RETRY_JITTER_MIN_S, _RETRY_JITTER_MAX_S)


class RetryModel(WrapperModel):
    """Up to N conditional retries on TimeoutError with jitter backoff.

    Fail-fast on provider-cluster evidence (session exclusion slug match):
    if the silent-hang alerter has already fired for this provider, we
    re-raise without sleeping so OpenRouter routes the next call through
    a different backend.
    """

    def __init__(
        self,
        wrapped,
        *,
        max_retries: int = _RETRY_MAX_RETRIES,
        backoff_range: tuple[float, float] = (_RETRY_JITTER_MIN_S, _RETRY_JITTER_MAX_S),
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter_fn: Callable[[], float] | None = None,
    ):
        super().__init__(wrapped)
        self._max_retries = max_retries
        self._backoff_range = backoff_range
        self._sleeper = sleeper
        self._jitter_fn = jitter_fn or (lambda: random.uniform(*backoff_range))

    @property
    def _provider_slug(self) -> str:
        return getattr(
            self.wrapped,
            "_provider_slug",
            _provider_slug_from_model_id(getattr(self.wrapped, "model_name", "unknown")),
        )

    @property
    def _agent_key(self) -> str:
        return getattr(self.wrapped, "_agent_key", "unknown")

    @property
    def _wrapped_model_name(self) -> str:
        return getattr(self.wrapped, "model_name", "unknown")

    def _should_fail_fast(self, exc: BaseException) -> bool:
        """Skip the retry-sleep when the *serving upstream* for this hop is
        already in the session exclusion set.

        Keys on the downstream upstream slug carried by `HopTimeout`, never
        the model author — an author-keyed check fail-fasted every agent
        the moment one provider-class cluster fired (2026-05-15 fleet
        kill-switch incident).

        Currently a deliberate no-op for the hop-timeout class: a
        `HopTimeout` never carries a non-None `downstream_provider` (the
        wall fires before OpenRouter reports the upstream — see the
        `HopTimeout` docstring + SWI-370), so this returns `False` and
        every timeout retries normally. That is the correct conservative
        default — when the upstream is unknown, OpenRouter may route the
        retry through a healthy backend. The path activates for free if a
        future producer ever populates `downstream_provider`.

        Routes through the same typed `downstream_provider_from_timeout`
        accessor every emit site uses, so a future rename of the
        `HopTimeout` field surfaces here too instead of silently
        degrading to a never-fail-fast path.
        """
        downstream = downstream_provider_from_timeout(exc)
        return bool(downstream) and downstream in get_dynamic_provider_excludes()

    async def _decide_retry_after_timeout(self, attempt: int, exc: BaseException) -> None:
        """Emit retry-decision span, sleep, or re-raise if cluster evidence exists."""
        if self._should_fail_fast(exc):
            emit_model_hop_retry_span(
                agent=self._agent_key,
                model_id=self._wrapped_model_name,
                provider=self._provider_slug,
                attempt=attempt,
                backoff_ms=0,
                outcome="fail_fast_cluster_evidence",
                logger=logger,
            )
            # Re-raise the timeout passed in, not a bare `raise` — keeps the
            # method correct if ever called outside an active except block.
            raise exc
        backoff_s = self._jitter_fn()
        emit_model_hop_retry_span(
            agent=self._agent_key,
            model_id=self._wrapped_model_name,
            provider=self._provider_slug,
            attempt=attempt + 1,
            backoff_ms=int(backoff_s * 1000),
            outcome="retry",
            logger=logger,
        )
        await self._sleeper(backoff_s)

    async def request(self, messages, model_settings, model_request_parameters):
        attempt = 0
        while True:
            try:
                return await super().request(messages, model_settings, model_request_parameters)
            except TimeoutError as timeout_exc:
                attempt += 1
                if attempt > self._max_retries:
                    raise
                await self._decide_retry_after_timeout(attempt, timeout_exc)

    @asynccontextmanager
    async def request_stream(
        self,
        messages,
        model_settings,
        model_request_parameters,
        run_context=None,
    ):
        # Streams can't be replayed once consumed; retry only the entrance
        # (first-byte wall). The inner HopTimingModel wraps __aenter__ in its
        # own wait_for, so a TimeoutError here comes from that wall.
        attempt = 0
        while True:
            try:
                stream_ctx = self.wrapped.request_stream(
                    messages, model_settings, model_request_parameters, run_context
                )
                break
            except TimeoutError as timeout_exc:
                attempt += 1
                if attempt > self._max_retries:
                    raise
                await self._decide_retry_after_timeout(attempt, timeout_exc)
        async with stream_ctx as response_stream:
            yield response_stream
