-- Migration 287: Remove dead tool_get_macro_affected_tickers from sector_aggregator
-- This tool was never registered (context=None) causing phantom tool ref warnings

UPDATE agent_prompts
SET enabled_tools = '{}',
    updated_at = NOW()
WHERE agent_key = 'sector_aggregator';
