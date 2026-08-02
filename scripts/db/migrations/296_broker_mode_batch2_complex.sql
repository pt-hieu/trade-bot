-- Batch 2: Switch 8 complex agents (3+ tools) to broker mode
-- Apply after batch 1 is validated via dry-run

-- alert_registrar: register_alert, list_active_alerts, remove_alert -> alert
UPDATE agent_prompts SET enabled_tools = ARRAY['alert']
WHERE agent_key = 'alert_registrar' AND is_active = TRUE;

-- entry_strategist: tool_search_articles, tool_read_article, tool_get_active_narratives -> article, narrative
UPDATE agent_prompts SET enabled_tools = ARRAY['article', 'narrative']
WHERE agent_key = 'entry_strategist' AND is_active = TRUE;

-- longterm: tool_get_watchlist, tool_get_longterm_config, tool_get_technicals, tool_read_research, tool_get_sector_allocation -> portfolio, technical
UPDATE agent_prompts SET enabled_tools = ARRAY['portfolio', 'technical']
WHERE agent_key = 'longterm' AND is_active = TRUE;

-- longterm_review: tool_get_valuation, tool_get_financial_comparison, tool_search_articles, tool_read_research, tool_get_valuation_history, tool_get_earnings_quality -> fundamental, article, portfolio
UPDATE agent_prompts SET enabled_tools = ARRAY['fundamental', 'article', 'portfolio']
WHERE agent_key = 'longterm_review' AND is_active = TRUE;

-- positions_thesis: tool_get_longterm_config, tool_search_articles, tool_get_active_narratives -> portfolio, article, narrative
UPDATE agent_prompts SET enabled_tools = ARRAY['portfolio', 'article', 'narrative']
WHERE agent_key = 'positions_thesis' AND is_active = TRUE;

-- positions_value: tool_get_valuation, tool_get_longterm_config, tool_get_valuation_history, tool_get_earnings_quality -> fundamental, portfolio
UPDATE agent_prompts SET enabled_tools = ARRAY['fundamental', 'portfolio']
WHERE agent_key = 'positions_value' AND is_active = TRUE;

-- sector_news: tool_search_articles, tool_read_article, tool_get_learnings, tool_get_active_narratives -> article, portfolio, narrative
UPDATE agent_prompts SET enabled_tools = ARRAY['article', 'portfolio', 'narrative']
WHERE agent_key = 'sector_news' AND is_active = TRUE;

-- synthesis_picks: tool_position_scale, tool_get_relative_strength, tool_get_stats -> portfolio, enrichment, statistic
UPDATE agent_prompts SET enabled_tools = ARRAY['portfolio', 'enrichment', 'statistic']
WHERE agent_key = 'synthesis_picks' AND is_active = TRUE;
