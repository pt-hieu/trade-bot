-- Wire belief tools to sub-agents that produce beliefs
-- Data-only migration — default connection works

UPDATE agent_prompts
SET enabled_tools = array_cat(enabled_tools, ARRAY['tool_get_my_beliefs', 'tool_get_belief_accuracy'])
WHERE agent_key IN (
    'sector_technical', 'sector_news', 'sector_enrichment',
    'positions_technical', 'positions_value', 'positions_thesis'
)
AND NOT 'tool_get_my_beliefs' = ANY(enabled_tools);
