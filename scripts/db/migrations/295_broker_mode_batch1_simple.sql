-- Batch 1: Switch 8 simple agents (1-2 tools) to broker mode
-- Broker detection: when ALL enabled_tools entries are valid domain names
-- These agents had 1-2 tools, so domain scope expansion is minimal

-- midday: tool_get_technicals -> technical
UPDATE agent_prompts SET enabled_tools = ARRAY['technical']
WHERE agent_key = 'midday' AND is_active = TRUE;

-- trading_mode: tool_get_technicals -> technical
UPDATE agent_prompts SET enabled_tools = ARRAY['technical']
WHERE agent_key = 'trading_mode' AND is_active = TRUE;

-- market_level: tool_search_articles -> article
UPDATE agent_prompts SET enabled_tools = ARRAY['article']
WHERE agent_key = 'market_level' AND is_active = TRUE;

-- sector_rotation: tool_search_sector_news -> article
UPDATE agent_prompts SET enabled_tools = ARRAY['article']
WHERE agent_key = 'sector_rotation' AND is_active = TRUE;

-- position_strategist: tool_get_longterm_config -> portfolio
UPDATE agent_prompts SET enabled_tools = ARRAY['portfolio']
WHERE agent_key = 'position_strategist' AND is_active = TRUE;

-- positions_aggregator: tool_get_ensemble_history -> portfolio
UPDATE agent_prompts SET enabled_tools = ARRAY['portfolio']
WHERE agent_key = 'positions_aggregator' AND is_active = TRUE;

-- positions_pev_alert: tool_get_comps, tool_get_thesis -> fundamental, portfolio
UPDATE agent_prompts SET enabled_tools = ARRAY['fundamental', 'portfolio']
WHERE agent_key = 'positions_pev_alert' AND is_active = TRUE;

-- sector_enrichment: tool_get_valuation_history, tool_get_block_trades -> fundamental, enrichment
UPDATE agent_prompts SET enabled_tools = ARRAY['fundamental', 'enrichment']
WHERE agent_key = 'sector_enrichment' AND is_active = TRUE;
