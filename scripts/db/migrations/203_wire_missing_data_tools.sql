-- Migration 203: Wire missing data tools to agents
-- Adds 6 new agent tools to relevant agents' enabled_tools arrays.
-- Tools: block_trades, ensemble_history, refiner_patterns, alert_effectiveness,
--        strategy_performance, sector_allocation

-- sector_enrichment: + tool_get_block_trades
UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_block_trades}'::text[]
WHERE agent_key = 'sector_enrichment'
  AND NOT enabled_tools @> '{tool_get_block_trades}'::text[];

-- entry_strategist: + tool_get_block_trades, tool_get_refiner_patterns,
--                     tool_get_alert_effectiveness, tool_get_strategy_performance
UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_block_trades}'::text[]
WHERE agent_key = 'entry_strategist'
  AND NOT enabled_tools @> '{tool_get_block_trades}'::text[];

UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_refiner_patterns}'::text[]
WHERE agent_key = 'entry_strategist'
  AND NOT enabled_tools @> '{tool_get_refiner_patterns}'::text[];

UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_alert_effectiveness}'::text[]
WHERE agent_key = 'entry_strategist'
  AND NOT enabled_tools @> '{tool_get_alert_effectiveness}'::text[];

UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_strategy_performance}'::text[]
WHERE agent_key = 'entry_strategist'
  AND NOT enabled_tools @> '{tool_get_strategy_performance}'::text[];

-- positions_aggregator: + tool_get_ensemble_history
-- (currently has no tools — setting array directly)
UPDATE agent_prompts
SET enabled_tools = '{tool_get_ensemble_history}'::text[]
WHERE agent_key = 'positions_aggregator'
  AND (enabled_tools IS NULL OR enabled_tools = '{}');

-- synthesis_holdings: + tool_get_ensemble_history, tool_get_sector_allocation
UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_ensemble_history}'::text[]
WHERE agent_key = 'synthesis_holdings'
  AND NOT enabled_tools @> '{tool_get_ensemble_history}'::text[];

UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_sector_allocation}'::text[]
WHERE agent_key = 'synthesis_holdings'
  AND NOT enabled_tools @> '{tool_get_sector_allocation}'::text[];

-- synthesis_picks: + tool_get_strategy_performance
UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_strategy_performance}'::text[]
WHERE agent_key = 'synthesis_picks'
  AND NOT enabled_tools @> '{tool_get_strategy_performance}'::text[];

-- longterm: + tool_get_sector_allocation
UPDATE agent_prompts
SET enabled_tools = enabled_tools || '{tool_get_sector_allocation}'::text[]
WHERE agent_key = 'longterm'
  AND NOT enabled_tools @> '{tool_get_sector_allocation}'::text[];
