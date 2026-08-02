-- Migration 108: Remove hardcoded sector allocations from longterm_review system prompt
-- The orchestrator now injects live allocations from sector_allocations table into sector_summary

UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    $$Portfolio target allocation: 50% Technology, 35% Real Estate, 15% Banking. The user prompt will provide the live sector breakdown — use it to identify overweight vs underweight sectors. Prefer additions in underweight sectors; avoid adding to sectors already at or above their target allocation.$$,
    $$The user prompt will provide live target sector allocations and the current sector breakdown — use them to identify overweight vs underweight sectors. Prefer additions in underweight sectors; avoid adding to sectors already at or above their target allocation.$$
)
WHERE agent_key = 'longterm_review';
