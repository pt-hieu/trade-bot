-- Migration 238: Remove beliefs, catalysts, articles list, and company profile tools
-- Type: Data
-- Rollback: array_append the tools back to enabled_tools
--
-- These tools fetched data that is now batch-loaded in enrichment_loader.py and
-- injected as compact structured context into agent prompts.
-- tool_read_article and tool_search_articles are KEPT (agent-driven deep-dives).

-- Beliefs — now injected from batch-fetched enrichment data
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_my_beliefs'),
    updated_at = NOW()
WHERE agent_key IN (
    'sector_technical', 'sector_news', 'sector_enrichment',
    'positions_technical', 'positions_value', 'positions_thesis'
)
AND 'tool_get_my_beliefs' = ANY(enabled_tools);

-- Catalyst preview — now batch-fetched and injected
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_catalyst_preview'),
    updated_at = NOW()
WHERE agent_key IN ('entry_strategist', 'synthesis', 'synthesis_holdings', 'synthesis_picks')
AND 'tool_get_catalyst_preview' = ANY(enabled_tools);

-- Articles list — article summaries now injected. KEEP tool_read_article + tool_search_articles.
UPDATE agent_prompts
SET enabled_tools = array_remove(array_remove(enabled_tools, 'tool_list_articles'), 'tool_get_articles'),
    updated_at = NOW()
WHERE ('tool_list_articles' = ANY(enabled_tools) OR 'tool_get_articles' = ANY(enabled_tools));

-- Company profiles — now batch-fetched and injected
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_company_profile'),
    updated_at = NOW()
WHERE agent_key IN ('sector_technical', 'sector_enrichment', 'synthesis')
AND 'tool_get_company_profile' = ANY(enabled_tools);
