-- Fix sector_news and sector_enrichment prompts: both reference tools that are either
-- unregistered (tool_list_articles) or not in enabled_tools (tool_get_flow, tool_get_insider).
--
-- sector_news:
--   Prompt YOUR TOOLS section lists tool_list_articles as step 1 ("List recent articles for
--   each ticker"), but tool_list_articles is NOT registered in the tool registry AND is NOT
--   in enabled_tools. The LLM cannot call it, so it compensates by calling tool_search_articles
--   twice per ticker plus tool_read_article x2 + tool_get_learnings x2 + tool_get_active_narratives
--   = 7 tool calls per ticker. With consumer (3 tickers) or technology (1 ticker but confused),
--   this burns 21+ requests and hits request_limit=30.
--   Fix: remove tool_list_articles from YOUR TOOLS section. Articles are already pre-loaded
--   in articles_context injected before the prompt (via format_articles_block).
--
-- sector_enrichment:
--   Prompt references tool_get_flow and tool_get_insider in YOUR TOOLS section, but neither
--   is in enabled_tools (only tool_get_valuation_history, tool_get_block_trades,
--   tool_get_belief_accuracy). Flow and insider data is already context-injected via
--   ticker_briefings (TICKER_DATA_HEADER = "pre-loaded — do NOT call tool_get_technicals/flow/insider/RS").
--   Fix: remove tool_get_flow and tool_get_insider from YOUR TOOLS section and update
--   steps to reference pre-loaded briefing data instead.
--
-- Type: Data (UPDATE agent_prompts) — default connection works

BEGIN;

-- ── sector_news fixes ─────────────────────────────────────────────────────

-- Step 1: Remove tool_list_articles from YOUR TOOLS section and clarify data sources
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '## YOUR TOOLS
- tool_list_articles: List recent articles for a ticker
- tool_search_articles: Search articles by keyword
- tool_read_article: Read full article content (use UUID from tool_list_articles)
- tool_get_learnings: Get historical trading patterns and lessons',
    '## DATA SOURCES
- Pre-loaded articles: headlines and summaries injected above (scan for relevant ones)
- tool_search_articles: Search for articles by keyword or topic (use if pre-loaded articles miss a key topic)
- tool_read_article: Read full article content using the id shown in pre-loaded list
- tool_get_learnings: Get historical trading patterns and lessons
- tool_get_active_narratives: Get active market narratives for a ticker'
),
    updated_at = NOW()
WHERE agent_key = 'sector_news'
  AND is_active = true
  AND system_prompt LIKE '%tool_list_articles%';

-- Step 2: Update ANALYSIS PER TICKER to remove tool_list_articles step
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '## ANALYSIS PER TICKER
1. List recent articles for each ticker
2. Read key articles that could affect price (earnings, regulatory, sector news)
3. Check learnings for recurring patterns (e.g. "TCB typically rallies after Q results")
4. Assess sentiment: positive/negative/neutral catalyst pipeline',
    '## ANALYSIS PER TICKER
1. Scan pre-loaded articles above for each ticker (headlines + summaries are injected)
2. Use tool_read_article to deep-dive on articles with clear price impact potential
3. Use tool_search_articles only if a key topic is absent from the pre-loaded list
4. Check tool_get_learnings for recurring patterns (e.g. "TCB typically rallies after Q results")
5. Assess sentiment: positive/negative/neutral catalyst pipeline'
),
    updated_at = NOW()
WHERE agent_key = 'sector_news'
  AND is_active = true
  AND system_prompt LIKE '%List recent articles for each ticker%';

-- Step 3: Update FORBIDDEN section to reference pre-loaded data instead of tool returns
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Do NOT fabricate article content — only cite what tools return',
    '- Do NOT fabricate article content — only cite what is in the pre-loaded articles or tool returns'
),
    updated_at = NOW()
WHERE agent_key = 'sector_news'
  AND is_active = true
  AND system_prompt LIKE '%only cite what tools return%';

-- ── sector_enrichment fixes ───────────────────────────────────────────────

-- Step 4: Remove tool_get_flow and tool_get_insider from YOUR TOOLS — data is context-injected
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '## YOUR TOOLS
- tool_get_flow: Get foreign and institutional flow data
- tool_get_insider: Get insider trading activity
- tool_get_valuation_history: Get P/E, P/B trends and sector comparisons',
    '## DATA SOURCES
- Pre-loaded ticker briefings: flow (foreign/prop net), insider activity, relative strength
  are already injected above — do NOT call tools for this data
- tool_get_valuation_history: Get P/E, P/B trends and sector comparisons (call this)
- tool_get_block_trades: Get large block trade activity for a ticker (call this)'
),
    updated_at = NOW()
WHERE agent_key = 'sector_enrichment'
  AND is_active = true
  AND system_prompt LIKE '%tool_get_flow%';

-- Step 5: Update ANALYSIS PER TICKER for enrichment to reflect context-injected data
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '## ANALYSIS PER TICKER
1. Check foreign flow: net buying/selling, trend direction
2. Check insider activity: recent buys/sells by management
3. Check valuation: current P/E vs historical range, P/B relative to sector',
    '## ANALYSIS PER TICKER
1. Read pre-loaded ticker briefings: flow direction and insider activity are already injected
2. Call tool_get_valuation_history: current P/E vs historical range, P/B relative to sector
3. Call tool_get_block_trades: large block activity that confirms or contradicts flow signal'
),
    updated_at = NOW()
WHERE agent_key = 'sector_enrichment'
  AND is_active = true
  AND system_prompt LIKE '%Check foreign flow%';

-- Step 6: Update FORBIDDEN section for enrichment
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Do NOT fabricate flow amounts or insider names
- Do NOT extrapolate future flow from past data
- If tool returns no data, say "no data available" — do NOT assume neutral',
    '- Do NOT fabricate flow amounts or insider names — only use values from ticker briefings
- Do NOT extrapolate future flow from past data
- If briefing data is missing for flow/insider, say "no data available" — do NOT assume neutral
- If tool_get_valuation_history returns no data, say "no valuation history" — do NOT assume neutral'
),
    updated_at = NOW()
WHERE agent_key = 'sector_enrichment'
  AND is_active = true
  AND system_prompt LIKE '%fabricate flow amounts%';

COMMIT;
