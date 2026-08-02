-- Migration 119: Enable tool_get_comps for longterm_review and positions_pev_alert

UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_comps')
WHERE agent_key = 'longterm_review'
AND NOT ('tool_get_comps' = ANY(enabled_tools));

UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_comps')
WHERE agent_key = 'positions_pev_alert'
AND NOT ('tool_get_comps' = ANY(enabled_tools));
