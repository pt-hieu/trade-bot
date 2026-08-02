-- Migration 064: Add tool_get_rotation to watchlist_update agent
-- Gives the weekly watchlist agent access to daily sector rotation data

UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_rotation')
WHERE agent_key = 'watchlist_update'
  AND NOT ('tool_get_rotation' = ANY(COALESCE(enabled_tools, '{}'::text[])));
