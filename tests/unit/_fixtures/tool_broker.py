"""Shared async runner for tool_broker test splits."""

from __future__ import annotations

import asyncio


def _run_coro(coro):
    """Run an async callable on a dedicated event loop per call.

    Avoids the deprecated `asyncio.get_event_loop()` pattern which raises
    RuntimeError in Python 3.12 when test ordering leaves the default loop
    closed. `asyncio.run` creates + cleans up its own loop per invocation.
    """
    return asyncio.run(coro)
