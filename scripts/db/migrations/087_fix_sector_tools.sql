-- Migration 087: Restore sector agent tools lost in prior migrations
-- sector agent needs article + ticker data tools from registry

UPDATE agent_prompts
SET enabled_tools = '{tool_list_articles,tool_search_articles,tool_read_article,tool_get_ticker_data,tool_get_learnings}',
    updated_at = NOW()
WHERE agent_key = 'sector';
