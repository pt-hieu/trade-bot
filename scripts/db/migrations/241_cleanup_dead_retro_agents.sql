-- Migration 241: Delete dead retro agent configs
-- Type: Data (default DATABASE_URL works)
--
-- retro_evaluator: replaced by retro_commentary (migration 177)
-- retro_parser: function never called from pipeline (recommendation_builder replaced it)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/241_cleanup_dead_retro_agents.sql

DELETE FROM agent_prompts WHERE agent_key = 'retro_evaluator' AND is_active = TRUE;
DELETE FROM agent_prompts WHERE agent_key = 'retro_parser' AND is_active = TRUE;
