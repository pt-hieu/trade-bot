-- Migration 052: Remove goal tools from non-director agents
-- Strategy director now owns goal-awareness. Other agents get goal context
-- from the directive, not via tools.

-- Synthesis: replace tool_get_capital with tool_get_cash (goal now from directive)
UPDATE agent_prompts SET enabled_tools = array_remove(enabled_tools, 'tool_get_capital')
WHERE agent_key = 'synthesis';
UPDATE agent_prompts SET enabled_tools = array_append(enabled_tools, 'tool_get_cash')
WHERE agent_key = 'synthesis' AND NOT ('tool_get_cash' = ANY(enabled_tools));

-- Refiner: replace tool_get_capital with tool_get_cash
UPDATE agent_prompts SET enabled_tools = array_remove(enabled_tools, 'tool_get_capital')
WHERE agent_key = 'refiner';
UPDATE agent_prompts SET enabled_tools = array_append(enabled_tools, 'tool_get_cash')
WHERE agent_key = 'refiner' AND NOT ('tool_get_cash' = ANY(enabled_tools));

-- Midday: remove tool_get_goal (gets directive from DB instead)
UPDATE agent_prompts SET enabled_tools = array_remove(enabled_tools, 'tool_get_goal')
WHERE agent_key = 'midday';

-- Strategy director: replace tool_get_capital with tool_get_cash (goals fetched in Python)
UPDATE agent_prompts SET enabled_tools = array_remove(enabled_tools, 'tool_get_capital')
WHERE agent_key = 'strategy_director';
UPDATE agent_prompts SET enabled_tools = array_append(enabled_tools, 'tool_get_cash')
WHERE agent_key = 'strategy_director' AND NOT ('tool_get_cash' = ANY(enabled_tools));
