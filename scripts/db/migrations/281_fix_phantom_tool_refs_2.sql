-- Migration 281: Fix 2 phantom tool refs that crashed daily scan 2026-04-02 (run 23924250632)
--
-- market_level: prompt says "call tool_get_learnings(...)" but enabled_tools=['tool_search_articles']
-- positions_technical: prompt says "do NOT call tool_get_belief_accuracy" — negative ref still triggers regex
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py 281

-- market_level: replace tool_get_learnings call with context reference
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before classifying regime, call tool_get_learnings(query="macro_patterns") to check regime accuracy history.',
    'Before classifying regime, review the regime accuracy history pre-loaded in context above.'
)
WHERE agent_key = 'market_level'
  AND system_prompt LIKE '%tool_get_learnings%';

-- positions_technical: reword to avoid tool name in negative reference
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Your calibration data is pre-loaded in context above (do NOT call tool_get_belief_accuracy).',
    'Your calibration data is pre-loaded in context above — no tool calls needed.'
)
WHERE agent_key = 'positions_technical'
  AND system_prompt LIKE '%tool_get_belief_accuracy%';
