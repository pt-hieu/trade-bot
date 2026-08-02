-- Drop vestigial model_tier column — all agents use model_id directly
ALTER TABLE agent_prompts DROP COLUMN IF EXISTS model_tier;
