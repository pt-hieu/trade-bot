-- Migration 211: Bump critic max_tokens to 96000
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Root cause: critic hit 20K output ceiling → PydanticAI error → double timeout (600s wasted)
-- All agents should be 96000 — the critic exception is now proven harmful.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/211_critic_max_tokens.sql

UPDATE agent_prompts SET max_tokens = 96000 WHERE agent_key = 'critic';
