#!/usr/bin/env python3
"""
Fix sector_news and sector_enrichment prompts: both reference tools that are either
unregistered (tool_list_articles) or not in enabled_tools (tool_get_flow, tool_get_insider).

sector_news:
  Prompt YOUR TOOLS section lists tool_list_articles as step 1 ("List recent articles for
  each ticker"), but tool_list_articles is NOT registered in the tool registry AND is NOT
  in enabled_tools. The LLM cannot call it, so it compensates by calling tool_search_articles
  twice per ticker plus tool_read_article x2 + tool_get_learnings x2 + tool_get_active_narratives
  = 7 tool calls per ticker. With consumer (3 tickers) or technology (1 ticker but confused),
  this burns 21+ requests and hits request_limit=30.
  Fix: remove tool_list_articles from YOUR TOOLS section. Articles are already pre-loaded
  in articles_context injected before the prompt (via format_articles_block).

sector_enrichment:
  Prompt references tool_get_flow and tool_get_insider in YOUR TOOLS section, but neither
  is in enabled_tools (only tool_get_valuation_history, tool_get_block_trades,
  tool_get_belief_accuracy). Flow and insider data is already context-injected via
  ticker_briefings (TICKER_DATA_HEADER = "pre-loaded -- do NOT call tool_get_technicals/flow/insider/RS").
  Fix: remove tool_get_flow and tool_get_insider from YOUR TOOLS section and update
  steps to reference pre-loaded briefing data instead.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.env import load_env

load_env()

from shared.database import Database, close_db

logger = logging.getLogger(__name__)

# ── Replacement specs: (agent_key, search_text, replacement_text) ──────────

REPLACEMENTS = [
    # sector_news: Step 1 — replace YOUR TOOLS section to remove tool_list_articles
    (
        "sector_news",
        "## YOUR TOOLS\n- tool_list_articles: List recent articles for a ticker\n"
        "- tool_search_articles: Search articles by keyword\n"
        "- tool_read_article: Read full article content (use UUID from tool_list_articles)\n"
        "- tool_get_learnings: Get historical trading patterns and lessons",
        "## DATA SOURCES\n"
        "- Pre-loaded articles: headlines and summaries injected above (scan for relevant ones)\n"
        "- tool_search_articles: Search for articles by keyword or topic (use if pre-loaded articles miss a key topic)\n"
        "- tool_read_article: Read full article content using the id shown in pre-loaded list\n"
        "- tool_get_learnings: Get historical trading patterns and lessons\n"
        "- tool_get_active_narratives: Get active market narratives for a ticker",
    ),
    # sector_news: Step 2 — update ANALYSIS PER TICKER to remove tool_list_articles step
    (
        "sector_news",
        "## ANALYSIS PER TICKER\n"
        "1. List recent articles for each ticker\n"
        "2. Read key articles that could affect price (earnings, regulatory, sector news)\n"
        '3. Check learnings for recurring patterns (e.g. "TCB typically rallies after Q results")\n'
        "4. Assess sentiment: positive/negative/neutral catalyst pipeline",
        "## ANALYSIS PER TICKER\n"
        "1. Scan pre-loaded articles above for each ticker (headlines + summaries are injected)\n"
        "2. Use tool_read_article to deep-dive on articles with clear price impact potential\n"
        "3. Use tool_search_articles only if a key topic is absent from the pre-loaded list\n"
        '4. Check tool_get_learnings for recurring patterns (e.g. "TCB typically rallies after Q results")\n'
        "5. Assess sentiment: positive/negative/neutral catalyst pipeline",
    ),
    # sector_news: Step 3 — update FORBIDDEN section
    (
        "sector_news",
        "- Do NOT fabricate article content — only cite what tools return",
        "- Do NOT fabricate article content — only cite what is in the pre-loaded articles or tool returns",
    ),
    # sector_enrichment: Step 4 — replace YOUR TOOLS section to remove tool_get_flow/tool_get_insider
    (
        "sector_enrichment",
        "## YOUR TOOLS\n"
        "- tool_get_flow: Get foreign and institutional flow data\n"
        "- tool_get_insider: Get insider trading activity\n"
        "- tool_get_valuation_history: Get P/E, P/B trends and sector comparisons",
        "## DATA SOURCES\n"
        "- Pre-loaded ticker briefings: flow (foreign/prop net), insider activity, relative strength\n"
        "  are already injected above — do NOT call tools for this data\n"
        "- tool_get_valuation_history: Get P/E, P/B trends and sector comparisons (call this)\n"
        "- tool_get_block_trades: Get large block trade activity for a ticker (call this)",
    ),
    # sector_enrichment: Step 5 — update ANALYSIS PER TICKER
    (
        "sector_enrichment",
        "## ANALYSIS PER TICKER\n"
        "1. Check foreign flow: net buying/selling, trend direction\n"
        "2. Check insider activity: recent buys/sells by management\n"
        "3. Check valuation: current P/E vs historical range, P/B relative to sector",
        "## ANALYSIS PER TICKER\n"
        "1. Read pre-loaded ticker briefings: flow direction and insider activity are already injected\n"
        "2. Call tool_get_valuation_history: current P/E vs historical range, P/B relative to sector\n"
        "3. Call tool_get_block_trades: large block activity that confirms or contradicts flow signal",
    ),
    # sector_enrichment: Step 6 — update FORBIDDEN section
    (
        "sector_enrichment",
        "- Do NOT fabricate flow amounts or insider names\n"
        "- Do NOT extrapolate future flow from past data\n"
        '- If tool returns no data, say "no data available" — do NOT assume neutral',
        "- Do NOT fabricate flow amounts or insider names — only use values from ticker briefings\n"
        "- Do NOT extrapolate future flow from past data\n"
        '- If briefing data is missing for flow/insider, say "no data available" — do NOT assume neutral\n'
        '- If tool_get_valuation_history returns no data, say "no valuation history" — do NOT assume neutral',
    ),
]


async def run():
    async with Database() as db:
        for agent_key, old_text, new_text in REPLACEMENTS:
            # Fetch current prompt
            rows = await db.fetch_all(
                "SELECT id, system_prompt FROM agent_prompts WHERE agent_key = $1 AND is_active = true",
                agent_key,
            )
            if not rows:
                logger.warning("No active agent_prompts row for %s", agent_key)
                continue

            row = rows[0]
            current_prompt = row["system_prompt"]

            if old_text not in current_prompt:
                # Try to diagnose the mismatch
                # Check if it's a dash/unicode issue by looking for key substring
                first_line = old_text.split("\n")[0]
                if first_line in current_prompt:
                    logger.warning(
                        "Partial match for %s: first line found but full block not matched. "
                        "Check whitespace/unicode differences.",
                        agent_key,
                    )
                else:
                    logger.info(
                        "Search text not found in %s prompt (already applied or different content).",
                        agent_key,
                    )
                continue

            updated_prompt = current_prompt.replace(old_text, new_text, 1)
            await db.execute(
                "UPDATE agent_prompts SET system_prompt = $1, updated_at = NOW() "
                "WHERE agent_key = $2 AND is_active = true",
                updated_prompt,
                agent_key,
            )
            print(f"Updated {agent_key}: replaced '{first_line_preview(old_text)}'")

    await close_db()


def first_line_preview(text: str) -> str:
    return text.split("\n")[0][:60]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
