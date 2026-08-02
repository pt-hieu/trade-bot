-- Migration 248: Switch critic agent to MiniMax-M2.5
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Reason: Critic was timing out (300s, bumped to 600s in Fix 2) on Kimi-K2.5.
-- MiniMax-M2.5 is faster and already used as fallback model in model.py.
-- Critic has no tools and a focused task (narrative review) — doesn't need
-- Kimi's extended thinking capabilities.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/248_critic_model_minimax.sql

UPDATE agent_prompts
SET model_id = 'MiniMaxAI/MiniMax-M2.5'
WHERE agent_key = 'critic';
