-- Migration 081: Critic-refiner loop optimization
-- 1. Refiner: drop tool_get_technicals + tool_calculate_trade_setup (R:R pre-computed)
-- 2. Synthesis: don't embed directive sections verbatim (they're prepended after loop)
-- 3. Critic: require only stock sections (not directive sections)
-- 4. Refiner: simplify R:R fix rule (remove = skip, not recalculate)

-- 1. Refiner tools: drop 2 technicals tools
UPDATE agent_prompts
SET enabled_tools = ARRAY['tool_get_holdings', 'tool_get_cash', 'tool_get_articles']
WHERE agent_key = 'refiner';

-- 2. Synthesis: replace verbatim embedding instruction with context-only
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'You MUST embed ALL directive sections VERBATIM at the top of your output. Do NOT rephrase, recalculate, or omit any directive section. Do NOT call tools to re-fetch data that the directive already provides.',
    E'These directive sections are CONTEXT for your decisions. Do NOT embed them in your output.\nThe directive will be prepended to the final brief automatically. Use the directive to:\n- Understand the current stance, regime, and capital status\n- Apply position guidance for MY HOLDINGS\n- Respect trading mode and entry criteria'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%embed ALL directive sections VERBATIM%';

-- Synthesis: replace header label from "embed" to "CONTEXT ONLY"
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'## CRITICAL: Strategy Directive Sections\nYou will receive a STRATEGY DIRECTIVE',
    E'## CRITICAL: Strategy Directive Sections (CONTEXT ONLY)\nYou will receive a STRATEGY DIRECTIVE'
)
WHERE agent_key = 'synthesis'
  AND system_prompt NOT LIKE '%CONTEXT ONLY%';

-- Synthesis: replace "After embedding the directive, generate ONLY these sections"
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'## Your Job: Stock-Level Analysis\nAfter embedding the directive, generate ONLY these sections:',
    E'## Your Job: Stock-Level Sections ONLY\nGenerate ONLY these sections:'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%After embedding the directive%';

-- Synthesis: replace output format instruction
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'## Output Format (PLAIN ASCII, NO MARKDOWN)\n\nFirst: Embed ALL directive sections verbatim (TODAY''S THEME through KEY RISK).\n\nThen generate:\n\nMY HOLDINGS',
    E'## Output Format (PLAIN ASCII, NO MARKDOWN)\n\nStart directly with MY HOLDINGS. Do NOT include directive sections in your output.\n\nMY HOLDINGS'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%First: Embed ALL directive sections verbatim%';

-- Synthesis: update output constraints
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'## Output Constraints\n- Do NOT output per-sector stock lists\n- Only output directive sections + MY HOLDINGS through WHAT TO DO TODAY\n- Keep total output under 3000 characters for Telegram delivery\n- PLAIN ASCII only, no markdown, no emojis',
    E'## Output Constraints\n- Do NOT output per-sector stock lists\n- Do NOT output directive sections (THEME, STANCE, GOAL PROGRESS, etc.) -- they are prepended automatically\n- Output ONLY: MY HOLDINGS, LONG-TERM PORTFOLIO, TOP PICKS, SKIP THESE, WHAT TO DO TODAY\n- Keep total output under 2000 characters (directive sections add ~1000 chars)\n- PLAIN ASCII only, no markdown, no emojis'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%Only output directive sections + MY HOLDINGS%';

-- 3. Critic: replace Section Compliance to remove directive sections from required list
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'### 8. Section Compliance (CRITICAL)\nRequired sections (ALL must be present):\n- GOAL PROGRESS\n- CAPITAL STATUS\n- GLOBAL CONTEXT\n- MARKET MOOD\n- NEWS THAT MATTERS\n- MY HOLDINGS\n- LONG-TERM PORTFOLIO\n- TOP PICKS\n- SKIP THESE\n- WHAT TO DO TODAY',
    E'### 8. Section Compliance (CRITICAL)\nThe brief you review contains ONLY stock-level sections. Directive sections (GOAL PROGRESS, CAPITAL STATUS, etc.) are provided separately as STRATEGY DIRECTIVE context and will be prepended to the final output automatically.\n\nRequired sections in the brief (ALL must be present):\n- MY HOLDINGS\n- LONG-TERM PORTFOLIO\n- TOP PICKS\n- SKIP THESE\n- WHAT TO DO TODAY\n\nNOTE: Do NOT flag missing GOAL PROGRESS, CAPITAL STATUS, GLOBAL CONTEXT, MARKET MOOD, NEWS THAT MATTERS -- these come from the directive, not the synthesis.'
)
WHERE agent_key = 'critic'
  AND system_prompt LIKE '%GOAL PROGRESS%CAPITAL STATUS%GLOBAL CONTEXT%';

-- 4. Refiner: add directive context note at start of system_prompt
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'Your job is to fix issues identified by the critic and produce a corrected version.',
    E'Your job is to fix issues identified by the critic and produce a corrected version.\n\nIMPORTANT: You receive ONLY the stock-level sections of the brief (MY HOLDINGS, LONG-TERM PORTFOLIO, TOP PICKS, SKIP THESE, WHAT TO DO TODAY). A STRATEGY DIRECTIVE is provided separately as context. Do NOT include directive sections in your refined output.\n\n## Your Tools (3 total)\n1. tool_get_holdings() -- Verify portfolio tickers and P/L\n2. tool_get_cash() -- Check actual deployable cash\n3. tool_get_articles() -- Get today''s news headlines if NEWS section missing\n\nNOTE: R:R ratios are pre-computed from real levels. Do NOT recalculate using tool_get_technicals. If R:R is flagged invalid, REMOVE that pick (add to SKIP THESE) rather than recalculating.'
)
WHERE agent_key = 'refiner'
  AND system_prompt NOT LIKE '%stock-level sections of the brief%';

-- Refiner: replace R:R fix rule to remove technicals recalculation
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'### Fixing R:R Issues\nFor BUY recommendations with missing or invalid R:R:\n- Use tool_get_technicals(ticker) to get actual support/resistance levels\n- Calculate Entry from nearest_support or current price\n- Calculate Stop from swing_low or range_20d_low (1-2% below)\n- Calculate Target from swing_high or range_20d_high\n- R:R = (Target - Entry) / (Entry - Stop)\n- If R:R < 3.0 after recalculation, REMOVE the recommendation\n- Replace with "Skipped - R:R insufficient" in SKIP THESE section',
    E'### Fixing R:R Issues\nFor BUY recommendations with missing or invalid R:R:\n- R:R values are pre-computed -- if flagged invalid, REMOVE the recommendation\n- Replace with "Skipped - R:R insufficient" in SKIP THESE section\n- Do NOT attempt to recalculate R:R from technicals'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%tool_get_technicals(ticker) to get actual support%';
