-- Migration 298: Drop enabled_tools column from agent_prompts
-- Type: DDL (requires owner connection)
--
-- All agents now get full tool access via broker (no domain restrictions).
-- The enabled_tools column is no longer read by any code path.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/298_drop_enabled_tools_column.sql

ALTER TABLE agent_prompts DROP COLUMN IF EXISTS enabled_tools;
