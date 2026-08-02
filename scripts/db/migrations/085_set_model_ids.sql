-- Migration 084: Set explicit model_id on alert_analyst + macro_interpreter
-- Both tier 'critic' and 'light' resolve to MiniMaxAI/MiniMax-M2.5.
-- Setting model_id explicitly matches all other agents and surfaces correctly in web graph.

UPDATE agent_prompts
SET model_id = 'MiniMaxAI/MiniMax-M2.5', updated_at = NOW()
WHERE agent_key IN ('alert_analyst', 'macro_interpreter')
  AND model_id IS NULL;
