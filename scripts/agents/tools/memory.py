"""
Memory tools for trading agents.

Provides episodic memory (similar past days) and semantic memory (trading rules).

All tools return a "prose" field with natural language summaries.
Agents should PREFER using the prose field for analysis.
"""

from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)

from agents.memory.embeddings import embed_context
from shared.neon import (
    find_applicable_rules,
    find_similar_days,
    find_similar_patterns,
)

MemoryQueryType = Literal["similar_days", "similar_patterns", "trading_rules"]


# ============================================================================
# Prose Formatters - Convert dict data to natural language strings
# ============================================================================


def _format_similar_days_prose(days: list[dict], interpretation: str) -> str:
    """Convert similar days list to natural prose."""
    if not days:
        return "No similar historical days found with embeddings."

    parts = [f"Similar Historical Days ({len(days)} found):"]

    for i, day in enumerate(days, 1):
        date = day.get("date", "?")
        sim = day.get("similarity", "?")
        regime = day.get("regime", "?")
        mode = day.get("mode", "?")
        win_rate = day.get("win_rate", "N/A")
        best = day.get("best_call", "N/A")
        insight = day.get("insight", "")

        line = f"{i}. {date} ({sim} match): {regime}, {mode} mode."
        if win_rate != "N/A":
            line += f" Win rate {win_rate}."
        if best and best != "N/A":
            line += f" Best: {best}."
        if insight:
            line += f" Insight: {insight}"
        parts.append(line)

    if interpretation:
        parts.append(interpretation)

    return " ".join(parts)


def _format_trading_rules_prose(rules: list[dict], entry: list, exit_r: list, avoid: list) -> str:
    """Convert trading rules list to natural prose."""
    if not rules:
        return "No trading rules found for current conditions."

    parts = [f"Trading Rules for Current Context ({len(rules)} found):"]

    for rule in rules:
        name = rule.get("rule", "?")
        rtype = rule.get("type", "?").upper()
        conf = rule.get("confidence", "?")
        sample = rule.get("sample_size", 0)

        line = f'{rtype}: "{name}" ({conf} confidence)'
        if sample:
            line += f" Sample: {sample} trades."
        parts.append(line)

    return " ".join(parts)


def _format_winning_patterns_prose(patterns: list[dict], regime: str, hot_sectors: str) -> str:
    """Convert winning patterns list to natural prose."""
    if not patterns:
        return "No similar winning patterns found."

    ctx = f"{regime}"
    if hot_sectors:
        ctx += f" + {hot_sectors}"

    parts = [f"Winning Patterns for {ctx} ({len(patterns)} found):"]

    for i, p in enumerate(patterns, 1):
        pattern = p.get("pattern", "?")
        sim = p.get("similarity", "?")
        win_rate = p.get("win_rate", "N/A")
        rule = p.get("rule", "")
        sample = p.get("sample_size", 0)

        line = f'{i}. "{pattern}" ({sim} match): Win rate {win_rate}'
        if sample:
            line += f", sample {sample}"
        line += "."
        if rule:
            line += f" Rule: {rule}"
        parts.append(line)

    return " ".join(parts)


def _format_losing_patterns_prose(patterns: list[dict], regime: str) -> str:
    """Convert losing patterns list to natural prose."""
    if not patterns:
        return "No similar losing patterns found."

    parts = [f"Patterns to Avoid for {regime} ({len(patterns)} found):"]

    for i, p in enumerate(patterns, 1):
        pattern = p.get("pattern", "?")
        sim = p.get("similarity", "?")
        win_rate = p.get("win_rate", "N/A")
        rule = p.get("rule", "")

        line = f'{i}. "{pattern}" ({sim} match): Win rate {win_rate}.'
        if rule:
            line += f" Avoid: {rule}"
        parts.append(line)

    return " ".join(parts)


async def get_similar_historical_days(
    current_context: dict,
    limit: int = 3,
    min_similarity: float = 0.5,
) -> list[dict]:
    """
    Find past days with similar market conditions.

    Returns days with their outcomes for context-aware recommendations.

    Args:
        current_context: Dict with market context fields like:
            - market_regime: RISK_ON, NEUTRAL, RISK_OFF
            - global_macro: CALM, CAUTIOUS, ELEVATED, CRISIS
            - hot_sectors: List of hot sector names
            - cold_sectors: List of cold sector names
            - vix: VIX value
        limit: Maximum number of results
        min_similarity: Minimum similarity score (0-1)

    Returns:
        List of similar days with outcomes and insights
    """
    # Generate embedding for current context
    embedding = embed_context(current_context)

    # Find similar days
    similar_days = await find_similar_days(embedding, limit=limit, min_similarity=min_similarity)

    # Format for agent consumption
    return [
        {
            "date": str(day["record_date"]),
            "similarity": f"{day['similarity']:.0%}",
            "regime": day["market_regime"],
            "mode": day["trading_mode"],
            "win_rate": f"{day['win_rate']:.0f}%" if day["win_rate"] else "N/A",
            "best_call": day["best_call"],
            "worst_call": day["worst_call"],
            "insight": day["key_insight"],
        }
        for day in similar_days
    ]


async def get_similar_patterns_for_context(
    context: dict,
    pattern_type: str = "winning",
    limit: int = 3,
    min_similarity: float = 0.5,
) -> list[dict]:
    """
    Find learning patterns similar to current context.

    Args:
        context: Dict with context fields for embedding
        pattern_type: "winning" or "losing"
        limit: Maximum results
        min_similarity: Minimum similarity score (0-1)

    Returns:
        List of similar patterns with rules
    """
    embedding = embed_context(context)

    patterns = await find_similar_patterns(
        embedding,
        pattern_type=pattern_type,
        limit=limit,
        min_similarity=min_similarity,
    )

    return [
        {
            "pattern": p["pattern_description"],
            "similarity": f"{p['similarity']:.0%}",
            "win_rate": f"{p['win_rate']:.0f}%" if p["win_rate"] else "N/A",
            "rule": p["actionable_rule"] if pattern_type == "winning" else p["avoid_rule"],
            "sample_size": p["sample_size"],
        }
        for p in patterns
    ]


async def get_trading_rules_for_context(
    regime: str | None = None,
    sectors: list[str] | None = None,
    rsi: float | None = None,
    macro: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Get trading rules applicable to current context.

    Args:
        regime: Market regime (RISK_ON, NEUTRAL, RISK_OFF)
        sectors: List of relevant sectors (e.g., ["banking", "real_estate"])
        rsi: Current RSI value (filters by condition_rsi_range)
        macro: Global macro regime (CALM, CAUTIOUS, ELEVATED, CRISIS)
        limit: Maximum results

    Returns:
        List of applicable rules sorted by confidence
    """
    rules = await find_applicable_rules(
        regime=regime,
        sectors=sectors,
        rsi=rsi,
        macro=macro,
        limit=limit,
    )

    return [
        {
            "rule": rule.get("description") or rule["rule_name"],
            "type": rule["rule_type"],
            "action": rule["action"],
            "confidence": f"{rule['confidence']:.0%}",
            "sample_size": rule["sample_size"],
        }
        for rule in rules
    ]


# ============================================================================
# Agent Tool Functions - Return string for LLM agents
# ============================================================================


async def tool_get_similar_days(
    regime: str,
    hot_sectors: str = "",
    cold_sectors: str = "",
    macro: str | None = None,
    vix: float | None = None,
) -> str:
    """
    Find past days with similar market context and their outcomes.

    Use this to calibrate expectations based on historical performance.

    Args:
        regime: Current market regime (RISK_ON, NEUTRAL, RISK_OFF)
        hot_sectors: Comma-separated hot sectors (e.g., "banking,real_estate")
        cold_sectors: Comma-separated cold sectors
        macro: Global macro regime (CALM, CAUTIOUS, ELEVATED, CRISIS)
        vix: Current VIX value

    For use by LLM agents. Returns natural prose string.
    """
    try:
        context = {
            "market_regime": regime,
            "global_macro": macro if macro else None,
            "hot_sectors": hot_sectors.split(",") if hot_sectors else [],
            "cold_sectors": cold_sectors.split(",") if cold_sectors else [],
            "vix": vix,
        }

        similar = await get_similar_historical_days(context, limit=3, min_similarity=0.5)

        if not similar:
            return "No similar historical days found with embeddings."

        interpretation = _interpret_similar_days(similar)
        return _format_similar_days_prose(similar, interpretation)
    except Exception as e:
        return f"Memory search unavailable: {e}"


async def tool_get_trading_rules(
    regime: str,
    sectors: str = "",
    rsi: float | None = None,
    macro: str | None = None,
) -> str:
    """
    Get validated trading rules for current conditions.

    Rules are derived from historical patterns with confidence scores.

    Args:
        regime: Market regime (RISK_ON, NEUTRAL, RISK_OFF)
        sectors: Comma-separated sectors (e.g., "banking,technology")
        rsi: Current RSI value for filtering
        macro: Global macro regime

    For use by LLM agents. Returns natural prose string.
    """
    try:
        sector_list = sectors.split(",") if sectors else None

        rules = await get_trading_rules_for_context(
            regime=regime,
            sectors=sector_list,
            rsi=rsi,
            macro=macro if macro else None,
            limit=5,
        )

        if not rules:
            return "No trading rules found for current conditions."

        entry_rules = [r for r in rules if r["type"] == "entry"]
        exit_rules = [r for r in rules if r["type"] == "exit"]
        avoid_rules = [r for r in rules if r["type"] == "avoid"]

        return _format_trading_rules_prose(rules, entry_rules, exit_rules, avoid_rules)
    except Exception as e:
        return f"Trading rules lookup failed: {e}"


async def tool_get_winning_patterns(
    regime: str,
    hot_sectors: str = "",
) -> str:
    """
    Find winning patterns similar to current conditions.

    Args:
        regime: Current market regime
        hot_sectors: Comma-separated hot sectors

    For use by LLM agents. Returns natural prose string.
    """
    try:
        context = {
            "market_regime": regime,
            "hot_sectors": hot_sectors.split(",") if hot_sectors else [],
        }

        patterns = await get_similar_patterns_for_context(
            context,
            pattern_type="winning",
            limit=3,
        )

        if not patterns:
            return "No similar winning patterns found."

        return _format_winning_patterns_prose(patterns, regime, hot_sectors)
    except Exception as e:
        return f"Pattern search unavailable: {e}"


async def tool_get_losing_patterns(
    regime: str,
    cold_sectors: str = "",
) -> str:
    """
    Find losing patterns to avoid in current conditions.

    Args:
        regime: Current market regime
        cold_sectors: Comma-separated cold sectors

    For use by LLM agents. Returns natural prose string.
    """
    try:
        context = {
            "market_regime": regime,
            "cold_sectors": cold_sectors.split(",") if cold_sectors else [],
        }

        patterns = await get_similar_patterns_for_context(
            context,
            pattern_type="losing",
            limit=3,
        )

        if not patterns:
            return "No similar losing patterns found."

        return _format_losing_patterns_prose(patterns, regime)
    except Exception as e:
        return f"Pattern search unavailable: {e}"


def _interpret_similar_days(days: list[dict]) -> str:
    """Generate interpretation text from similar days."""
    if not days:
        return "No historical data available for comparison."

    # Calculate average win rate
    win_rates = []
    for d in days:
        wr = d.get("win_rate", "N/A")
        if wr != "N/A":
            try:
                win_rates.append(float(wr.strip("%")) / 100)
            except (ValueError, AttributeError):
                logger.warning("Corrupt win_rate value for similar day: %r", wr)

    avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else None

    # Build interpretation
    parts = [f"Found {len(days)} similar trading days."]

    if avg_win_rate is not None:
        if avg_win_rate >= 0.6:
            parts.append(
                f"Historical win rate in similar conditions: {avg_win_rate:.0%} (favorable)."
            )
        elif avg_win_rate >= 0.4:
            parts.append(f"Historical win rate: {avg_win_rate:.0%} (mixed).")
        else:
            parts.append(f"Historical win rate: {avg_win_rate:.0%} (challenging - be cautious).")
    else:
        parts.append(
            "INSUFFICIENT DATA — win rates unavailable for matched days. "
            "Default to CAUTIOUS posture per fail-closed policy."
        )

    # Common insights
    insights = [d.get("insight") for d in days if d.get("insight")]
    if insights:
        parts.append(f"Key insight: {insights[0]}")

    return " ".join(parts)
