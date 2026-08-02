"""Total-timeout wrapper for `Agent.run()` — required for disable_fallback agents.

httpx's per-chunk read timeout never fires on first-byte silence, and agents
configured with `disable_fallback: true` skip FallbackModel rollover (see
c5b995dd). Without this guard, a silent provider hang eats the full outer
phase wall.

On TimeoutError this helper emits a `silent_provider_hang` span (the same
span pipeline-review queries via `hang_type="silent_provider"`) and re-raises
so the caller's existing degradation path runs.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.observability import emit_silent_provider_hang_span

from .model.wrappers import (
    await_with_hop_unwrap,
    downstream_provider_from_timeout,
    provider_slug_from_timeout,
)
from .tools.agent_deps import AgentDeps

logger = logging.getLogger(__name__)


async def run_agent_with_total_timeout(
    agent: Any,
    prompt: str,
    *,
    agent_name: str,
    deps: AgentDeps,
    total_timeout_s: float = 60.0,
    usage_limits: Any = None,
    sector: str | None = None,
) -> Any:
    """Wrap `agent.run()` under a total-timeout wall.

    Args:
        agent: PydanticAI Agent instance.
        prompt: Prompt text forwarded to `agent.run()`.
        agent_name: Used in the silent_provider_hang span for alerting.
        deps: REQUIRED. AgentDeps forwarded to `agent.run(deps=...)`. The
            framework's `prepare_tools` callback dereferences
            `ctx.deps.unlocked` at boundary entry; passing `None` raises
            AttributeError before any model byte is emitted (SWI-180).
        total_timeout_s: Hard wall. 60s matches the `_get_provider` default.
        usage_limits: Passed through to `agent.run()` unchanged.
        sector: Optional sector tag attached to the silent_provider_hang
            span when the wall fires (sector-scoped agents only).

    Returns:
        Whatever `agent.run()` returned on success.

    Raises:
        TimeoutError: Forwarded after span emission.
        Any other exception: Re-raised unchanged.
    """
    try:
        return await await_with_hop_unwrap(
            agent.run(prompt, deps=deps, usage_limits=usage_limits),
            timeout=total_timeout_s,
        )
    except TimeoutError as timeout_exc:
        emit_silent_provider_hang_span(
            agent=agent_name,
            wall_s=int(total_timeout_s),
            exception_type=type(timeout_exc).__name__,
            logger=logger,
            provider=provider_slug_from_timeout(timeout_exc),
            downstream_provider=downstream_provider_from_timeout(timeout_exc),
            sector=sector,
        )
        raise
