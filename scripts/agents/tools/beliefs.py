"""Belief continuity and accuracy tools for agent personas."""

import asyncio
import logging
from datetime import date

logger = logging.getLogger(__name__)

# Thresholds for predicted-vs-reality formatting
_ACCURATE_THRESHOLD_PP = 3  # within 3pp = "accurate"
_BIAS_PATTERN_THRESHOLD = 0.05  # 5pp overcall triggers bias warning
_POOR_CALIBRATION_BRIER = 0.5  # Brier above this = worse than naive


async def tool_get_my_beliefs(
    scan_date: date,
    agent_key: str,
    ticker: str = "all",
) -> str:
    """Retrieve your prior beliefs for belief continuity.

    Args:
        scan_date: Current analysis date (from context)
        agent_key: Your agent identity (from context)
        ticker: Specific ticker or "all" for all prior beliefs
    """
    try:
        from shared.neon import get_prior_beliefs

        beliefs = await get_prior_beliefs(agent_key, scan_date)
    except Exception as error:
        logger.warning(
            "tool_get_my_beliefs failed for agent=%s ticker=%s: %s", agent_key, ticker, error
        )
        return "Belief data unavailable. Proceed with NEW beliefs for all tickers."

    if not beliefs:
        return "No prior beliefs found. All beliefs today will be NEW."

    if ticker != "all":
        beliefs = [b for b in beliefs if b["ticker"] == ticker]
        if not beliefs:
            return f"No prior belief for {ticker}. Your belief will be NEW."

    lines = ["Your prior beliefs:"]
    for belief in beliefs:
        days_held = belief.get("days_held") or 1
        streak_note = f", held for {days_held}d" if days_held > 1 else ""
        lines.append(
            f"- {belief['ticker']}: {belief['direction']} "
            f"(bull={float(belief['bull_probability']):.0%} "
            f"base={float(belief['base_probability']):.0%} "
            f"bear={float(belief['bear_probability']):.0%}) "
            f"conviction={float(belief['conviction']):.0%}"
            f"{streak_note} "
            f"[{belief['belief_status']}, {belief['record_date']}]"
        )
        lines.append(f'  "{belief["belief_narrative"]}"')

    lines.append(
        "\nFor each ticker, REAFFIRM/UPDATE/REVERSE your prior belief "
        "or mark NEW if no prior exists."
    )
    return "\n".join(lines)


async def tool_get_belief_accuracy(
    agent_key: str,
    perspective: str = "self",
) -> str:
    """Get prediction accuracy and calibration data.

    Args:
        agent_key: Your agent identity (from context)
        perspective: "self" for your own stats, "all" for all agents
    """
    from shared.neon import (
        get_agent_belief_accuracy,
        get_all_belief_accuracy,
    )

    try:
        if perspective == "all":
            all_stats = await get_all_belief_accuracy(days_back=30)
        else:
            all_stats = None
    except Exception as error:
        logger.warning(
            "tool_get_belief_accuracy DB fetch failed for agent=%s: %s", agent_key, error
        )
        return "Belief accuracy data unavailable. Use your best judgment for conviction levels."

    if perspective == "all":
        if not all_stats:
            return "Insufficient data — form beliefs based on your analysis."

        lines = ["Belief Accuracy (30-day rolling, all agents):"]
        for agent, stats in sorted(all_stats.items()):
            scored = stats.get("scored_beliefs") or 0
            if scored == 0:
                continue
            brier = stats.get("avg_brier") or 0
            direction_accuracy = stats.get("direction_accuracy") or 0
            streak_accuracy = stats.get("accuracy_streak_3plus")
            streak_note = f" streak_3d+={streak_accuracy:.0%}" if streak_accuracy else ""
            lines.append(
                f"  {agent}: Brier={brier:.3f} "
                f"direction={direction_accuracy:.0%} "
                f"({scored} scored){streak_note}"
            )
        return "\n".join(lines)

    try:
        from shared.neon.belief_queries import compute_agent_prediction_vs_actual

        stats, (predicted_dist, actual_dist) = await asyncio.gather(
            get_agent_belief_accuracy(agent_key, days_back=30),
            compute_agent_prediction_vs_actual(agent_key, days_back=30),
        )
    except Exception as error:
        logger.warning(
            "tool_get_belief_accuracy DB fetch failed for agent=%s: %s", agent_key, error
        )
        return "Belief accuracy data unavailable. Use your best judgment for conviction levels."

    scored = stats.get("scored_beliefs") or 0
    if scored < 5:
        return (
            f"Insufficient data ({scored} scored beliefs). "
            "Form beliefs based on your analysis — calibration will improve with more data."
        )

    brier = stats.get("avg_brier") or 0
    direction_accuracy = stats.get("direction_accuracy") or 0
    avg_conviction = stats.get("avg_conviction") or 0
    streak_accuracy = stats.get("accuracy_streak_3plus")
    reversals = stats.get("reversals") or 0

    lines = [
        f"Your Belief Accuracy ({agent_key}, 30-day rolling):",
        f"  Brier score: {brier:.3f} (lower=better, 0=perfect, 0.667=random)",
        f"  Direction accuracy: {direction_accuracy:.0%}",
        f"  Avg conviction: {avg_conviction:.0%}",
        f"  Reversals: {reversals}",
    ]
    if streak_accuracy is not None:
        lines.append(f"  Streak (3d+) accuracy: {streak_accuracy:.0%}")

    # Predicted vs Reality distribution breakdown
    if predicted_dist and actual_dist:
        lines.append("")
        lines.append("  YOUR PREDICTIONS vs REALITY:")
        for direction in ("BULLISH", "NEUTRAL", "BEARISH"):
            pred_pct = predicted_dist.get(direction, 0) * 100
            actual_pct = actual_dist.get(direction, 0) * 100
            diff = pred_pct - actual_pct
            if abs(diff) < _ACCURATE_THRESHOLD_PP:
                note = "(accurate)"
            elif diff > 0:
                ratio = pred_pct / actual_pct if actual_pct > 0 else float("inf")
                if ratio > 2:
                    note = f"(over-calling by {ratio:.0f}x)"
                else:
                    note = f"(over-calling by {abs(diff):.0f}pp)"
            else:
                note = f"(under-calling by {abs(diff):.0f}pp)"
            lines.append(
                f"    You predicted {direction}: {pred_pct:.0f}% | "
                f"Actually {direction}: {actual_pct:.0f}% {note}"
            )

        # Identify the worst bias pattern
        worst_direction = ""
        worst_overcall = 0.0
        for direction in ("BULLISH", "NEUTRAL", "BEARISH"):
            overcall = predicted_dist.get(direction, 0) - actual_dist.get(direction, 0)
            if overcall > worst_overcall:
                worst_overcall = overcall
                worst_direction = direction

        if worst_direction and worst_overcall > _BIAS_PATTERN_THRESHOLD:
            lines.append("")
            lines.append(
                f"  PATTERN: You are systematically over-confident on {worst_direction}. "
                f"When you predict {worst_direction}, check if your evidence truly supports "
                f">{'+' if worst_direction == 'BULLISH' else '-'}1.5% movement in 5 days."
            )

    # Brier-based calibration note
    if brier > _POOR_CALIBRATION_BRIER:
        lines.append(
            "  WARNING: Brier > 0.5 — your predictions are worse than naive. "
            "Be more cautious with conviction."
        )

    return "\n".join(lines)
