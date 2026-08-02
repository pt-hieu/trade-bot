-- Agent Configuration in DB
-- Stores model IDs, temperature, retries, tool flags alongside prompts.
-- Enables runtime config changes without code deploys.

-- Add config columns to agent_prompts
ALTER TABLE agent_prompts
  ADD COLUMN IF NOT EXISTS model_id VARCHAR(100),
  ADD COLUMN IF NOT EXISTS temperature FLOAT,
  ADD COLUMN IF NOT EXISTS max_tokens INT,
  ADD COLUMN IF NOT EXISTS top_p FLOAT,
  ADD COLUMN IF NOT EXISTS output_retries INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS enabled_tools TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS model_settings JSONB DEFAULT '{}';

-- Add config snapshot to version history
ALTER TABLE agent_prompt_versions
  ADD COLUMN IF NOT EXISTS config_snapshot JSONB;

-- ============================================================================
-- Populate existing agents with current hardcoded values
-- ============================================================================

-- Heavy tier (Kimi K2.5) agents
UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', output_retries = 0
WHERE agent_key = 'critic';

UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', output_retries = 3
WHERE agent_key = 'sector';

UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', output_retries = 3
WHERE agent_key = 'positions';

UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', output_retries = 0
WHERE agent_key = 'refiner';

UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', output_retries = 0
WHERE agent_key = 'synthesis';

UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', output_retries = 3
WHERE agent_key = 'watchlist_update';

UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', output_retries = 3
WHERE agent_key = 'retro_evaluator';

UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', output_retries = 3
WHERE agent_key = 'retro_patterns';

-- Critic tier (GLM-4.5-Air) agents
UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 3
WHERE agent_key = 'market_level';

-- Light tier (GLM-4.5-Air) agents
UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 3
WHERE agent_key = 'trading_mode';

UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 3
WHERE agent_key = 'longterm';

UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 3
WHERE agent_key = 'midday';

UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 3
WHERE agent_key = 'sector_rotation';

UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 0
WHERE agent_key = 'alert_registrar';

UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 0
WHERE agent_key = 'retro_generator';

UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 3
WHERE agent_key = 'retro_parser';

UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 3
WHERE agent_key = 'positions_pev_verifier';

UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 3
WHERE agent_key = 'positions_pev_alert';

-- Predictor uses critic model, 2 retries, loads from file (not DB) currently
-- Skip predictor — it's not in agent_prompts table yet

-- Catalysts and capital_events (light tier)
UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 0
WHERE agent_key IN ('catalysts', 'capital_events');

-- Ensemble sub-agents (light tier for analysts, heavy for aggregator)
UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', output_retries = 3
WHERE agent_key IN ('positions_technical', 'positions_value', 'positions_thesis');

UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', output_retries = 3
WHERE agent_key = 'positions_aggregator';

-- ============================================================================
-- Populate enabled_tools for each agent
-- ============================================================================

UPDATE agent_prompts SET enabled_tools = '{}'
WHERE agent_key IN ('critic', 'retro_generator', 'retro_parser');

UPDATE agent_prompts SET enabled_tools = '{tool_get_vnindex,tool_get_rotation,tool_get_history,tool_search_news}'
WHERE agent_key = 'market_level';

UPDATE agent_prompts SET enabled_tools = '{tool_get_technicals,tool_get_holdings}'
WHERE agent_key = 'trading_mode';

UPDATE agent_prompts SET enabled_tools = '{tool_list_articles,tool_search_articles,tool_read_article,tool_get_ticker_data}'
WHERE agent_key = 'sector';

UPDATE agent_prompts SET enabled_tools = '{tool_get_holdings,tool_get_longterm_config,tool_get_technicals,tool_search_news}'
WHERE agent_key = 'positions';

UPDATE agent_prompts SET enabled_tools = '{tool_get_watchlist,tool_get_price_data,tool_read_research}'
WHERE agent_key = 'longterm';

UPDATE agent_prompts SET enabled_tools = '{tool_get_holdings,tool_get_cash_balance,tool_get_technicals,tool_get_goal,tool_get_trades,tool_get_midday_prices}'
WHERE agent_key = 'midday';

UPDATE agent_prompts SET enabled_tools = '{tool_get_technicals,tool_get_holdings,tool_get_cash,tool_get_capital,tool_get_articles,tool_calculate_trade_setup}'
WHERE agent_key = 'refiner';

UPDATE agent_prompts SET enabled_tools = '{tool_get_capital,tool_get_holdings,tool_get_trades,tool_get_learnings,tool_get_regime,tool_get_rotation,tool_get_macro,tool_position_scale,tool_similar_days,tool_trading_rules,tool_winning_patterns,tool_losing_patterns,tool_get_stats,tool_calculate_trade_setup}'
WHERE agent_key = 'synthesis';

UPDATE agent_prompts SET enabled_tools = '{tool_get_current_watchlist,tool_watchlist_technicals,tool_watchlist_search_news,tool_get_week_dates,tool_get_catalysts,tool_get_capital_events}'
WHERE agent_key = 'watchlist_update';

UPDATE agent_prompts SET enabled_tools = '{register_alert,list_active_alerts,remove_alert}'
WHERE agent_key = 'alert_registrar';

UPDATE agent_prompts SET enabled_tools = '{tool_get_sector_data,tool_get_regime,tool_search_sector_news,tool_get_rotation_history}'
WHERE agent_key = 'sector_rotation';

UPDATE agent_prompts SET enabled_tools = '{tool_get_executed_trades}'
WHERE agent_key = 'retro_evaluator';

UPDATE agent_prompts SET enabled_tools = '{tool_get_historical_evaluations}'
WHERE agent_key = 'retro_patterns';

-- positions_pev agents have no tools (tools used at orchestrator level)
UPDATE agent_prompts SET enabled_tools = '{}'
WHERE agent_key IN ('positions_pev_verifier', 'positions_pev_alert');

-- Catalysts and capital_events: inline tools (not from registry)
UPDATE agent_prompts SET enabled_tools = '{}'
WHERE agent_key IN ('catalysts', 'capital_events');

-- Ensemble sub-agents
UPDATE agent_prompts SET enabled_tools = '{tool_get_holdings,tool_get_technicals}'
WHERE agent_key = 'positions_technical';

UPDATE agent_prompts SET enabled_tools = '{tool_get_holdings,tool_get_valuation,tool_get_longterm_config}'
WHERE agent_key = 'positions_value';

UPDATE agent_prompts SET enabled_tools = '{tool_get_holdings,tool_get_longterm_config,tool_search_news}'
WHERE agent_key = 'positions_thesis';

UPDATE agent_prompts SET enabled_tools = '{}'
WHERE agent_key = 'positions_aggregator';
