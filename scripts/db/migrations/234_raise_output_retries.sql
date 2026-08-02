-- Raise output_retries to 2 for all active agents
-- Gives structured output parsing 2 extra attempts before failing
UPDATE agent_prompts
SET output_retries = 2,
    updated_at = NOW()
WHERE is_active = TRUE;
