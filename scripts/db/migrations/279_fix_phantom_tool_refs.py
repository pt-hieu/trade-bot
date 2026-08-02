#!/usr/bin/env python3
"""Migration 279: Fix phantom tool references in 14 agent system prompts.

Phantom tool refs = prompt text says "use tool_X" but tool_X is not in enabled_tools.
The LLM tries to call it, fails, and loops on available tools (burning tokens).
This is the 8th fix for this defect class (prior: migrations 239/242/243/247/275/276).

Type: Data (agent_prompts update, default DATABASE_URL works)
Usage: SWINGY_ENV=production uv run python scripts/db/migrations/279_fix_phantom_tool_refs.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Each entry: (agent_key, old_text, new_text)
# Replacements remove phantom tool refs and point to context-injected data instead.
REPLACEMENTS: list[tuple[str, str, str]] = [
    # --- bear_reviewer ---
    (
        "bear_reviewer",
        "Use tool_get_technicals to verify price action claims independently.",
        "Verify price action claims against the technical data injected above.",
    ),
    # --- bull_reviewer ---
    (
        "bull_reviewer",
        "Use tool_get_technicals to verify price action claims independently.",
        "Verify price action claims against the technical data injected above.",
    ),
    # --- capital_events ---
    (
        "capital_events",
        "- tool_get_current_events() \u2014 Get currently tracked capital events to avoid duplicates",
        "- Current events are pre-loaded in context above \u2014 check them to avoid duplicates",
    ),
    (
        "capital_events",
        "Always check tool_get_current_events() first to avoid duplicates.",
        "Always check the pre-loaded events in context above to avoid duplicates.",
    ),
    # --- catalysts ---
    (
        "catalysts",
        "- tool_get_current_catalysts() \u2014 Get currently tracked catalysts to avoid duplicates",
        "- Current catalysts are pre-loaded in context above \u2014 check them to avoid duplicates",
    ),
    (
        "catalysts",
        "- catalyst_id: ID from tool_get_current_catalysts()",
        "- catalyst_id: ID from the pre-loaded catalysts above",
    ),
    (
        "catalysts",
        "Avoid duplicates \u2014 always check tool_get_current_catalysts() first.",
        "Avoid duplicates \u2014 always check the pre-loaded catalysts above first.",
    ),
    # --- entry_strategist ---
    (
        "entry_strategist",
        "Before finalizing entries, call tool_get_catalyst_preview() to check exposure.",
        "Before finalizing entries, check the catalyst data injected in context above.",
    ),
    (
        "entry_strategist",
        "9. tool_list_articles(sector=X) \u2014 browse today\u2019s articles for a sector",
        "9. Articles are pre-loaded in context above \u2014 reference them directly",
    ),
    # tool_name is a false positive from "Do NOT include [tool_name]" — no change needed
    # --- midday ---
    (
        "midday",
        "1. tool_get_holdings() - Get current portfolio positions with P/L",
        "1. Holdings data is pre-loaded in context above (positions with P/L)",
    ),
    (
        "midday",
        "2. tool_get_cash_balance() - Get deployable cash and trading mode status",
        "2. Cash balance and trading mode are pre-loaded in context above",
    ),
    (
        "midday",
        "Compare morning recommendations against current holdings from tool_get_holdings.",
        "Compare morning recommendations against current holdings from the data injected above.",
    ),
    (
        "midday",
        "1. Call tool_get_cash_balance to determine trading mode",
        "1. Read the cash balance and trading mode from context above",
    ),
    (
        "midday",
        "2. Call tool_get_holdings for position context",
        "2. Read the holdings data from context above for position context",
    ),
    (
        "midday",
        "The Afternoon Plan MUST ONLY reference tickers that appear in tool_get_holdings() results.",
        "The Afternoon Plan MUST ONLY reference tickers that appear in the holdings data above.",
    ),
    # --- position_strategist ---
    (
        "position_strategist",
        "- Call tool_get_holdings() first to see all positions with P/L",
        "- Review the holdings data pre-loaded in context above for all positions with P/L",
    ),
    # --- positions_aggregator ---
    (
        "positions_aggregator",
        'Before finalizing beliefs, call tool_get_belief_accuracy(perspective="all") to see all agents\u2019 track records.',
        "Before finalizing beliefs, review the belief accuracy data injected in context above.",
    ),
    # --- positions_value ---
    (
        "positions_value",
        "- tool_get_holdings(): Portfolio positions with P/L, weight, plan_type",
        "- Holdings data (positions with P/L, weight, plan_type) is pre-loaded in context above",
    ),
    (
        "positions_value",
        "- DO NOT assume positions not returned by tool_get_holdings exist",
        "- DO NOT assume positions not shown in the holdings data above exist",
    ),
    # --- sector_aggregator ---
    (
        "sector_aggregator",
        'Before finalizing beliefs, call tool_get_belief_accuracy(perspective="all") to see all agents\u2019 track records.',
        "Before finalizing beliefs, review the belief accuracy data injected in context above.",
    ),
    # --- sector_rotation ---
    (
        "sector_rotation",
        "2. tool_get_regime() - Get current market regime",
        "2. Market regime is pre-loaded in context above",
    ),
    (
        "sector_rotation",
        "4. tool_get_rotation_history(sector, days_back, query_type) - Get historical rotation accuracy",
        "4. Historical rotation data is available via tool_get_learnings",
    ),
    # --- synthesis_holdings ---
    (
        "synthesis_holdings",
        "- tool_get_holdings: Get current holdings with P/L data",
        "- Holdings with P/L data are pre-loaded in context above",
    ),
    (
        "synthesis_holdings",
        "- tool_get_catalyst_preview: Check upcoming events for held stocks",
        "- Catalyst data for held stocks is pre-loaded in context above",
    ),
    (
        "synthesis_holdings",
        "- tool_get_flow: Foreign flow data per holding",
        "- Foreign flow data per holding is pre-loaded in context above",
    ),
    (
        "synthesis_holdings",
        "- tool_get_relative_strength: Holding strength vs VN-Index",
        "- Relative strength vs VN-Index is pre-loaded in context above",
    ),
    (
        "synthesis_holdings",
        "Use POSITION GUIDANCE decisions provided in context. Verify P/L via tool_get_holdings.",
        "Use POSITION GUIDANCE decisions provided in context. Verify P/L via holdings data above.",
    ),
    (
        "synthesis_holdings",
        "- Do NOT fabricate P/L numbers \u2014 use tool_get_holdings data",
        "- Do NOT fabricate P/L numbers \u2014 use the holdings data above",
    ),
    (
        "synthesis_holdings",
        "- DO NOT assume positions not returned by tool_get_holdings exist",
        "- DO NOT assume positions not shown in the holdings data above exist",
    ),
    # --- synthesis_picks ---
    (
        "synthesis_picks",
        "- tool_get_catalyst_preview: Check upcoming events for pick candidates",
        "- Catalyst data for pick candidates is pre-loaded in context above",
    ),
    # --- trading_mode ---
    (
        "trading_mode",
        "* Use tool_get_holdings to check position values (shares * avg_cost)",
        "* Check position values from the holdings data pre-loaded in context above",
    ),
]


async def apply_migration() -> None:
    """Apply all phantom tool ref fixes."""
    from shared.database import get_db

    database = await get_db()
    applied = 0
    skipped = 0
    failed = 0

    for agent_key, old_text, new_text in REPLACEMENTS:
        row = await database.fetch_one(
            "SELECT system_prompt FROM agent_prompts WHERE agent_key = $1",
            agent_key,
        )
        if not row or not row["system_prompt"]:
            logger.warning("SKIP %s: agent not found or empty prompt", agent_key)
            skipped += 1
            continue

        prompt = row["system_prompt"]
        if old_text not in prompt:
            logger.warning("SKIP %s: text not found: %s", agent_key, old_text[:60])
            skipped += 1
            continue

        new_prompt = prompt.replace(old_text, new_text, 1)
        await database.execute(
            "UPDATE agent_prompts SET system_prompt = $1 WHERE agent_key = $2",
            new_prompt,
            agent_key,
        )
        applied += 1
        logger.info("OK   %s: replaced '%s...'", agent_key, old_text[:50])

    logger.info("\nDone: %d applied, %d skipped, %d failed", applied, skipped, failed)


if __name__ == "__main__":
    asyncio.run(apply_migration())
