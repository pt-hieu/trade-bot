-- 161_retro_goal_math.sql
-- Add deterministic math rule to GOAL TRACKING section (Rule #9: Python computes, LLM cites)
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    'GOAL TRACKING (include if goal data is provided)
- Daily target needed: X VND/day',
    'GOAL TRACKING (include if goal data is provided)
- NEVER compute arithmetic yourself. Use ONLY the pre-computed GOAL MATH numbers provided in the prompt.
- If GOAL MATH section not provided, write "insufficient data for projection" — do NOT calculate.
- Daily target needed: X VND/day'
)
WHERE agent_key = 'retro_generator'
AND system_prompt NOT LIKE '%NEVER compute arithmetic yourself%';
