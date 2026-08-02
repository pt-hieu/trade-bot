"""Belief domain tools."""

from ..helpers import cached_tool_call
from ..registry import ToolDomain, register_domain_tool


async def get_accuracy(perspective: str = "self", *, _ctx: dict) -> str:
    """Get prediction accuracy and calibration data.

    Args:
        perspective: "self" for your own stats, "all" for all agents

    Returns:
        Prose. perspective='all': indented per-agent Brier / direction
        accuracy / scored count / optional 3d-streak. perspective='self':
        caller-only stats plus predicted-vs-actual distribution.
        "Insufficient data" / "unavailable" messages on edge cases.
    """
    from ...beliefs import tool_get_belief_accuracy as _impl

    agent_key = _ctx.get("agent_key") or "unknown"
    cache = _ctx.get("_tool_cache")

    return await cached_tool_call(
        cache,
        f"belief_accuracy:{agent_key}:{perspective}",
        lambda: _impl(agent_key, perspective),
    )


register_domain_tool(
    "belief.get_accuracy",
    ToolDomain.BELIEF,
    get_accuracy,
    context_keys=("agent_key", "_tool_cache"),
    returns_hint="prose — per-agent Brier + direction accuracy",
)
