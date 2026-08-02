-- Migration 239: Fix dangling tool references and remove aliases
-- Type: Data
-- Rollback: reverse the renames/removals
--
-- Found during tool audit: 3 agents reference tools that don't exist in the registry.

-- strategy_director: tool_similar_days should be tool_get_similar_days (renamed in migration 117)
UPDATE agent_prompts
SET enabled_tools = array_remove(array_append(enabled_tools, 'tool_get_similar_days'), 'tool_similar_days'),
    updated_at = NOW()
WHERE agent_key = 'strategy_director'
  AND 'tool_similar_days' = ANY(enabled_tools)
  AND NOT ('tool_get_similar_days' = ANY(enabled_tools));

-- sector_rotation: tool_get_rotation_history has no implementation — remove
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_rotation_history'),
    updated_at = NOW()
WHERE agent_key = 'sector_rotation'
  AND 'tool_get_rotation_history' = ANY(enabled_tools);

-- retro_patterns: tool_get_historical_evaluations has no implementation — remove
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_historical_evaluations'),
    updated_at = NOW()
WHERE agent_key = 'retro_patterns'
  AND 'tool_get_historical_evaluations' = ANY(enabled_tools);

-- Standardize aliases: replace alias names with canonical names in any remaining agents
-- tool_get_ticker_data → tool_get_technicals
UPDATE agent_prompts
SET enabled_tools = array_remove(array_append(enabled_tools, 'tool_get_technicals'), 'tool_get_ticker_data'),
    updated_at = NOW()
WHERE 'tool_get_ticker_data' = ANY(enabled_tools)
  AND NOT ('tool_get_technicals' = ANY(enabled_tools));

-- tool_get_cash_balance → tool_get_cash
UPDATE agent_prompts
SET enabled_tools = array_remove(array_append(enabled_tools, 'tool_get_cash'), 'tool_get_cash_balance'),
    updated_at = NOW()
WHERE 'tool_get_cash_balance' = ANY(enabled_tools)
  AND NOT ('tool_get_cash' = ANY(enabled_tools));

-- tool_get_articles → tool_list_articles
UPDATE agent_prompts
SET enabled_tools = array_remove(array_append(enabled_tools, 'tool_list_articles'), 'tool_get_articles'),
    updated_at = NOW()
WHERE 'tool_get_articles' = ANY(enabled_tools)
  AND NOT ('tool_list_articles' = ANY(enabled_tools));

-- tool_search_news → tool_search_articles
UPDATE agent_prompts
SET enabled_tools = array_remove(array_append(enabled_tools, 'tool_search_articles'), 'tool_search_news'),
    updated_at = NOW()
WHERE 'tool_search_news' = ANY(enabled_tools)
  AND NOT ('tool_search_articles' = ANY(enabled_tools));
