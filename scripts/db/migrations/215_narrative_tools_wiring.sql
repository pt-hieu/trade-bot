-- Migration 215: Wire narrative tools to positions_thesis and synthesis_holdings
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py 215_narrative_tools_wiring.sql

-- positions_thesis: add narrative context for thesis integrity checks
UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_active_narratives}'::text[]
WHERE agent_key = 'positions_thesis'
  AND NOT enabled_tools @> '{tool_get_active_narratives}'::text[];

-- synthesis_holdings: add narrative context for holdings analysis
UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_active_narratives}'::text[]
WHERE agent_key = 'synthesis_holdings'
  AND NOT enabled_tools @> '{tool_get_active_narratives}'::text[];
