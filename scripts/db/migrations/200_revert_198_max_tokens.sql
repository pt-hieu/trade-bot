-- Migration 200: Revert migration 198
-- Type: Data
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py 200_revert_198_max_tokens.sql

UPDATE agent_prompts SET max_tokens = 96000, updated_at = NOW()
WHERE agent_key != 'critic' AND max_tokens != 96000 AND is_active = true;

UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', updated_at = NOW()
WHERE agent_key IN ('macro_interpreter', 'narrative_labeler')
  AND model_id = 'zai-org/GLM-4.5-Air-FP8';
