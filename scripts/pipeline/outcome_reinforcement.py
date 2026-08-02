"""Outcome reinforcement — inject agent accuracy stats into prompts.

Queries v_agent_belief_accuracy view and formats a performance
summary block for injection as user-message prefix. System prompts
stay generic (from DB); reinforcement is runtime context.
"""

import logging

from shared.neon.beliefs import get_all_belief_accuracy

logger = logging.getLogger(__name__)


async def build_accuracy_context(agent_key: str, days_back: int = 30) -> str:
    """Build performance summary string for an agent.

    Returns empty string if no accuracy data available (new agents
    or agents without scored beliefs).

    Args:
        agent_key: Agent identifier matching agent_beliefs.agent_key
        days_back: Rolling window for accuracy stats (default 30 days)

    Returns:
        Formatted accuracy block for prompt prefix, or empty string.
    """
    try:
        all_accuracy = await get_all_belief_accuracy(days_back=days_back)
        stats = all_accuracy.get(agent_key)
        if not stats or (stats.get("scored_beliefs") or 0) < 5:
            return ""
        return _format_stats(stats)
    except Exception as e:
        logger.warning("Failed to build accuracy context for '%s': %s", agent_key, e)
        return ""


async def build_accuracy_contexts_batch(agent_keys: list[str]) -> dict[str, str]:
    """Build accuracy context for multiple agents in one DB call.

    Returns:
        Dict mapping agent_key -> formatted accuracy string (empty if no data).
    """
    try:
        all_accuracy = await get_all_belief_accuracy()
        result = {}
        for agent_key in agent_keys:
            stats = all_accuracy.get(agent_key)
            if not stats or (stats.get("scored_beliefs") or 0) < 5:
                result[agent_key] = ""
                continue
            result[agent_key] = _format_stats(stats)
        return result
    except Exception as e:
        logger.warning("Failed to build batch accuracy contexts: %s", e)
        return {key: "" for key in agent_keys}


def _format_stats(stats: dict) -> str:
    """Format accuracy stats dict into prompt context string."""
    scored = stats.get("scored_beliefs") or 0
    direction_accuracy = stats.get("direction_accuracy") or 0
    avg_conviction = stats.get("avg_conviction") or 0
    brier_30d = stats.get("brier_30d") or stats.get("avg_brier") or 0
    reversals = stats.get("reversals") or 0

    if brier_30d and brier_30d < 0.25:
        calibration = "EXCELLENT"
    elif brier_30d and brier_30d < 0.35:
        calibration = "GOOD"
    elif brier_30d and brier_30d < 0.45:
        calibration = "FAIR"
    else:
        calibration = "NEEDS IMPROVEMENT"

    direction_warning = ""
    if direction_accuracy < 0.40:
        direction_warning = (
            f"\nDIRECTION ALERT: {direction_accuracy:.0%} accuracy is near-random. "
            f"Your directional calls are not adding signal. "
            f"Be honest about uncertainty — NEUTRAL (within +/-1.5% in 5 days) "
            f"is the most common outcome."
        )

    conviction_cap = ""
    if brier_30d and brier_30d > 0.50:
        conviction_cap = (
            f"\nCONVICTION CAP: Brier {brier_30d:.3f} > 0.50 — "
            f"cap conviction at 0.50. High conviction is not earned."
        )

    return (
        f"## YOUR TRACK RECORD (30-day rolling, {scored} scored beliefs)\n"
        f"Direction accuracy: {direction_accuracy:.0%} | "
        f"Avg conviction: {avg_conviction:.2f} | "
        f"Brier: {brier_30d:.3f}\n"
        f"Calibration: {calibration} | Reversals: {reversals}\n"
        f"Use this to calibrate your confidence — "
        f"{'trust your judgment' if calibration in ('EXCELLENT', 'GOOD') else 'be more cautious'}."
        f"{direction_warning}{conviction_cap}"
    )
