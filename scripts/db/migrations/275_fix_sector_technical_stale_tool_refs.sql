-- Fix sector_technical prompt: references tool_get_ticker_data, tool_get_relative_strength,
-- and tool_calculate_trade_setup — but all technical data is now context-injected via
-- ticker_briefings. These stale references cause the LLM to call the only available tool
-- (tool_get_belief_accuracy) in a 30-iteration loop, burning 430K tokens.
--
-- Also removes tool_get_belief_accuracy from enabled_tools since accuracy data
-- should be injected or the agent should work without it (no tool calls needed).
--
-- Type: Data (UPDATE agent_prompts) — default connection works

BEGIN;

-- Step 1: Replace YOUR TOOLS section — data is now pre-loaded in ticker briefings
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '## YOUR TOOLS
- tool_get_ticker_data: Get price levels, RSI, MACD, volume, ATR, pattern data
- tool_get_relative_strength: Compare ticker strength vs VN-Index

## ANALYSIS PER TICKER
For each ticker, gather data via tools and assess:',
    '## DATA SOURCE
All technical data (price, RSI, MACD, MAs, volume, ATR, patterns, relative strength)
is pre-loaded in the ticker briefings above. Do NOT call any tools for this data.

## ANALYSIS PER TICKER
For each ticker, use the pre-loaded data to assess:'
),
    updated_at = NOW()
WHERE agent_key = 'sector_technical'
  AND is_active = true
  AND system_prompt LIKE '%tool_get_ticker_data%';

-- Step 2: Replace TOOL USAGE RULES — no tools needed, data is injected
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '## TOOL USAGE RULES
- DO NOT compute your own R:R ratios — use tool_calculate_trade_setup instead
- DO NOT round or approximate values — use exact numbers returned by tools
- DO NOT interpret RSI<30 as automatic BUY — check for bullish confirmation first
- DO NOT fabricate entry/stop/target — tools compute them from actual S/R levels
- DO NOT recommend trades where tool_calculate_trade_setup returns valid=False',
    '## DATA USAGE RULES
- DO NOT compute your own R:R ratios — use the pre-computed trade_setup in ticker briefings
- DO NOT round or approximate values — use exact numbers from the briefings
- DO NOT interpret RSI<30 as automatic BUY — check for bullish confirmation first
- DO NOT fabricate entry/stop/target — use the pre-computed values from briefings
- DO NOT recommend trades where trade_setup shows valid=False'
),
    updated_at = NOW()
WHERE agent_key = 'sector_technical'
  AND is_active = true
  AND system_prompt LIKE '%tool_calculate_trade_setup instead%';

-- Step 3: Replace TOOL RETRY GUARDRAIL — no longer needed
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '## TOOL RETRY GUARDRAIL
If a tool call returns an error or empty result:
- Do NOT retry the exact same call with identical arguments.
- Try alternative arguments OR proceed without that data.
- After 2 consecutive failed tool calls, stop calling tools and work with available data.',
    '## MISSING DATA HANDLING
If any ticker briefing is incomplete or missing fields:
- Note the gap in your reasoning
- Proceed with available data — do not hallucinate missing values
- Lower confidence for tickers with incomplete data'
),
    updated_at = NOW()
WHERE agent_key = 'sector_technical'
  AND is_active = true
  AND system_prompt LIKE '%TOOL RETRY GUARDRAIL%';

-- Step 4: Fix FORBIDDEN section
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Do NOT fabricate data — only use values returned by tools
- Do NOT predict specific prices
- If a tool call fails, proceed with available data and note the gap',
    '- Do NOT fabricate data — only use values from the pre-loaded ticker briefings
- Do NOT predict specific prices
- If briefing data is missing for a ticker, note the gap in your reasoning'
),
    updated_at = NOW()
WHERE agent_key = 'sector_technical'
  AND is_active = true
  AND system_prompt LIKE '%only use values returned by tools%';

-- Step 5: Clear enabled_tools — sector_technical needs zero tools now
UPDATE agent_prompts
SET enabled_tools = '{}',
    updated_at = NOW()
WHERE agent_key = 'sector_technical'
  AND is_active = true;

COMMIT;
