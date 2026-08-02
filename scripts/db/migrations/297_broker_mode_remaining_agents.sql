-- Migrate remaining agents with tools to broker mode (local DB extras + production extras)

-- positions: tool_get_longterm_config, tool_get_technicals, tool_search_articles -> portfolio, technical, article
UPDATE agent_prompts SET enabled_tools = ARRAY['portfolio', 'technical', 'article']
WHERE agent_key = 'positions' AND is_active = TRUE AND enabled_tools @> ARRAY['tool_get_longterm_config'];

-- retro_evaluator: tool_get_executed_trades -> portfolio
UPDATE agent_prompts SET enabled_tools = ARRAY['portfolio']
WHERE agent_key = 'retro_evaluator' AND is_active = TRUE AND enabled_tools @> ARRAY['tool_get_executed_trades'];

-- sector_aggregator: tool_get_macro_affected_tickers -> company
UPDATE agent_prompts SET enabled_tools = ARRAY['company']
WHERE agent_key = 'sector_aggregator' AND is_active = TRUE AND enabled_tools @> ARRAY['tool_get_macro_affected_tickers'];

-- sector_technical: tool_get_relative_strength, tool_get_company_profile, tool_get_belief_accuracy, tool_get_technicals -> enrichment, company, belief, technical
UPDATE agent_prompts SET enabled_tools = ARRAY['enrichment', 'company', 'belief', 'technical']
WHERE agent_key = 'sector_technical' AND is_active = TRUE AND enabled_tools @> ARRAY['tool_get_technicals'];

-- longterm_review (local has more tools than prod): ensure domain coverage
UPDATE agent_prompts SET enabled_tools = ARRAY['fundamental', 'article', 'portfolio']
WHERE agent_key = 'longterm_review' AND is_active = TRUE AND NOT (enabled_tools <@ ARRAY['fundamental', 'article', 'portfolio', 'alert', 'belief', 'company', 'enrichment', 'market', 'memory', 'narrative', 'statistic', 'technical']);

-- synthesis_picks (local has tool_calculate_trade_setup extra): add technical domain
UPDATE agent_prompts SET enabled_tools = ARRAY['portfolio', 'enrichment', 'statistic', 'technical']
WHERE agent_key = 'synthesis_picks' AND is_active = TRUE AND NOT (enabled_tools <@ ARRAY['fundamental', 'article', 'portfolio', 'alert', 'belief', 'company', 'enrichment', 'market', 'memory', 'narrative', 'statistic', 'technical']);
