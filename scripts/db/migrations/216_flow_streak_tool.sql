-- Migration 216: Wire flow streak tool to entry_strategist and sector_enrichment
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py 216_flow_streak_tool.sql

-- entry_strategist: foreign flow streak for entry timing
UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_flow_streak}'::text[]
WHERE agent_key = 'entry_strategist'
  AND NOT enabled_tools @> '{tool_get_flow_streak}'::text[];

-- sector_enrichment: per-ticker flow streak context
UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_flow_streak}'::text[]
WHERE agent_key = 'sector_enrichment'
  AND NOT enabled_tools @> '{tool_get_flow_streak}'::text[];
