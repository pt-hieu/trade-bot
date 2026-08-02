"""Bounded-concurrency primitive for sibling-agent LLM fan-out.

Ensembles that fan out multiple LLM-agent coroutines on one OpenRouter key
(sector analysts, positions analysts, watchlist sector evaluators) must cap
concurrent inflight requests. Empirically, concurrent inflight requests hit
tail-latency stalls past the per-hop wall — serial Kimi was 0% hang vs
parallel Kimi 30-60% (2026-04-20 incident, re-confirmed by the 2026-05-15
sector fan-out incident).

Each ensemble previously hand-rolled its own `asyncio.Semaphore` + `_gated`
wrapper; this module is the single shared home so the cap is tuned and
tested in one place (CLAUDE.md: single derivation path).

Scope boundary: this primitive gates already-constructed coroutines and does
no error handling. The high-volume labeling orchestrators
(`article_sentiment_runner`, `news_relevance`, `news_extractor`) keep their
own inline `asyncio.Semaphore` because they construct AND error-handle the
coroutine inside the gate — a shape `gated_fanout` deliberately does not
support (see the eager-creation contract on `gated_fanout`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

_T = TypeVar("_T")


def gated_fanout(limit: int = 1) -> Callable[[Awaitable[_T]], Awaitable[_T]]:
    """Return a ``_gated(coro)`` wrapper admitting at most ``limit`` coroutines concurrently.

    Usage::

        gate = gated_fanout()  # limit=1 — strict serialization
        results = await asyncio.gather(gate(coro_a), gate(coro_b), gate(coro_c))

    The default ``limit=1`` strictly serializes a sibling-analyst trio so
    peak inflight LLM requests stay at 1 per ensemble. With N ensembles
    running concurrently under an outer rate-limit semaphore (e.g.
    ``phase_parallel`` ``_API_SEMAPHORE``), total peak inflight is N —
    matching that outer semaphore's intended cap instead of N × trio_size.
    Standalone ensembles with no outer semaphore (e.g. the weekly
    watchlist) may pass ``limit > 1`` to trade peak inflight for wall time.

    Call this *inside* the async function that uses it — the ``Semaphore``
    is created here and binds to the running event loop at call time. Do
    NOT hoist ``_gated = gated_fanout()`` to module scope; that
    re-introduces the cross-loop-binding bug ``phase_parallel``
    ``_API_SEMAPHORE`` is separately guarded against.

    Contract: ``_gated`` takes an ALREADY-CREATED coroutine. The semaphore
    serializes *execution*, not construction — so at the call site build
    every coroutine with an expression that cannot itself raise (call an
    ``async def`` directly, or a plain builder whose body cannot throw).
    If a sibling argument raises while
    ``asyncio.gather(_gated(a), _gated(b))`` is being assembled, the
    already-built coroutines leak unawaited.
    """
    semaphore = asyncio.Semaphore(limit)

    async def _gated(coro: Awaitable[_T]) -> _T:
        async with semaphore:
            return await coro

    return _gated
