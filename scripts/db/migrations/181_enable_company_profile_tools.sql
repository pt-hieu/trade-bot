-- Migration 181: Enable company profile tools for relevant agents
-- Data-only — default DATABASE_URL works

-- Company profile tool for sector sub-agents + synthesis + entry_strategist
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_company_profile'),
    updated_at = NOW()
WHERE agent_key IN ('sector_technical', 'sector_enrichment', 'synthesis', 'entry_strategist', 'midday_holdings')
  AND NOT ('tool_get_company_profile' = ANY(coalesce(enabled_tools, '{}')));

-- Macro-affected tickers lookup for synthesis + sector_aggregator
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_macro_affected_tickers'),
    updated_at = NOW()
WHERE agent_key IN ('synthesis', 'sector_aggregator')
  AND NOT ('tool_get_macro_affected_tickers' = ANY(coalesce(enabled_tools, '{}')));
