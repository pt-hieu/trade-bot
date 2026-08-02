-- Remove regime tools from agents that now get regime via context injection
UPDATE agent_prompts
SET enabled_tools = array_remove(
        array_remove(
            array_remove(enabled_tools, 'tool_get_regime'),
            'tool_get_history'),
        'tool_get_vnindex'),
    updated_at = NOW()
WHERE ('tool_get_regime' = ANY(enabled_tools)
    OR 'tool_get_history' = ANY(enabled_tools)
    OR 'tool_get_vnindex' = ANY(enabled_tools));
