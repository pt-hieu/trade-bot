-- Migration 199: Prompt quality fixes
-- Type: Data
--
-- 5b: Move tool guardrails from docstrings to system prompts
-- 5c: Fix refiner conflicting free-text output rules with structured output guidance
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/199_prompt_quality_fixes.sql

-- 5b: Append TOOL USAGE RULES to sector_technical and synthesis_picks
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## TOOL USAGE RULES\n- DO NOT compute your own R:R ratios — use tool_calculate_trade_setup instead\n- DO NOT round or approximate values — use exact numbers returned by tools\n- DO NOT interpret RSI<30 as automatic BUY — check for bullish confirmation first\n- DO NOT fabricate entry/stop/target — tools compute them from actual S/R levels\n- DO NOT recommend trades where tool_calculate_trade_setup returns valid=False',
    updated_at = NOW()
WHERE agent_key IN ('sector_technical', 'synthesis_picks')
  AND system_prompt NOT LIKE '%## TOOL USAGE RULES%';

-- 5b: Append PORTFOLIO TOOL RULES to holdings-related agents
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## PORTFOLIO TOOL RULES\n- DO NOT override pre-computed trailing stops — they are MANDATORY\n- DO NOT assume positions not returned by tool_get_holdings exist\n- DO NOT recalculate P/L percentages — use values returned exactly\n- DO NOT recommend BUY when deployable cash is 0\n- DO NOT use total_cash for sizing — use the deployable field',
    updated_at = NOW()
WHERE agent_key IN ('synthesis_holdings', 'positions_technical', 'positions_value', 'positions_thesis')
  AND system_prompt NOT LIKE '%## PORTFOLIO TOOL RULES%';

-- 5c: Fix refiner — replace conflicting free-text output rules with structured output guidance
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    '- Return ONLY the refined brief text',
    '- Return a RefinerResult JSON with `brief` (complete refined text) and `overrides` (list of structural changes)'
),
    updated_at = NOW()
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%Return ONLY the refined brief text%';

UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    '- Start directly with the first section header (GOAL PROGRESS or CONTEXT)',
    '- The `brief` field must start with the first stock section (MY HOLDINGS or CONTEXT)'
),
    updated_at = NOW()
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%Start directly with the first section header%';
