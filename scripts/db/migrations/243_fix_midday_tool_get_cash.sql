-- Migration 243: Remove dangling tool_get_cash from midday agent
-- Type: Data
-- Rollback: array_append(enabled_tools, 'tool_get_cash') WHERE agent_key = 'midday'
--
-- Migration 235 tried to remove tool_get_cash_balance from midday, but midday
-- actually had tool_get_cash (not tool_get_cash_balance). The array_remove was
-- a no-op, leaving a dangling reference that crashes the tool registry.

UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_cash'),
    updated_at = NOW()
WHERE agent_key = 'midday'
  AND 'tool_get_cash' = ANY(enabled_tools);
