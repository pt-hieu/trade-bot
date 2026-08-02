-- Set model_id for longterm_review agent (was NULL since migration 103)
UPDATE agent_prompts
SET model_id = 'moonshotai/Kimi-K2.5', updated_at = NOW()
WHERE agent_key = 'longterm_review' AND model_id IS NULL;
