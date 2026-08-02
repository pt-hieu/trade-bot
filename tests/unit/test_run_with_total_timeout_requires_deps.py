"""run_agent_with_total_timeout requires `deps=` (SWI-180 cutover).

The 2026-05-04 sector_aggregator no-op showed that omitting `deps=` at
the wrapper boundary lets `ctx.deps = None` flow into PydanticAI's
`prepare_tools` callback, which raises AttributeError before any model
byte is emitted. The wrapper signature change makes `deps` a required
keyword argument so omission fails at the function-call boundary
(TypeError) rather than silently inside the framework.
"""

from __future__ import annotations

import asyncio

import pytest

from agents.run_with_total_timeout import run_agent_with_total_timeout


def test_wrapper_requires_deps_kwarg() -> None:
    class _DummyAgent:
        async def run(self, *_args, **_kwargs):  # pragma: no cover - never reached
            raise AssertionError("run should not be called when deps is missing")

    with pytest.raises(TypeError):
        asyncio.run(
            run_agent_with_total_timeout(
                _DummyAgent(),
                "prompt",
                agent_name="test",
            )
        )
