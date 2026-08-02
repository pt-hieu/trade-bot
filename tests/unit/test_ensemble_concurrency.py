"""Tests for gated_fanout — the shared bounded-concurrency primitive for
sibling-agent LLM fan-out (sector / positions / watchlist ensembles).

The 2026-05-15 incident root cause: an unbounded 3-analyst fan-out per
sector, 4 sectors concurrent → 12 inflight LLM requests on one key. These
tests lock the invariant that `gated_fanout(limit)` admits at most `limit`
coroutines concurrently.
"""

from __future__ import annotations

import asyncio

import pytest

from agents.ensemble_concurrency import gated_fanout


class _ConcurrencyProbe:
    """Tracks peak concurrent entries across gated coroutines."""

    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    async def task(self, value: int) -> int:
        self.current += 1
        self.peak = max(self.peak, self.current)
        # Yield control so a broken gate would let siblings interleave.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.current -= 1
        return value


@pytest.mark.asyncio
async def test_gated_fanout_default_serializes_strictly():
    """Default limit=1 → peak concurrency is exactly 1 across the fan-out."""
    probe = _ConcurrencyProbe()
    gate = gated_fanout()

    results = await asyncio.gather(*(gate(probe.task(i)) for i in range(5)))

    assert probe.peak == 1
    assert results == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_gated_fanout_limit_two_admits_two():
    """limit=2 → peak concurrency reaches 2 but never exceeds it."""
    probe = _ConcurrencyProbe()
    gate = gated_fanout(2)

    await asyncio.gather(*(gate(probe.task(i)) for i in range(6)))

    assert probe.peak == 2


@pytest.mark.asyncio
async def test_gated_fanout_propagates_exceptions():
    """A failing gated coroutine propagates; the semaphore is still released
    so siblings are not deadlocked."""
    gate = gated_fanout()

    async def _boom() -> int:
        raise ValueError("analyst failed")

    async def _ok() -> int:
        return 42

    with pytest.raises(ValueError, match="analyst failed"):
        await gate(_boom())

    # Semaphore released despite the exception — a follow-up call still runs.
    assert await gate(_ok()) == 42
