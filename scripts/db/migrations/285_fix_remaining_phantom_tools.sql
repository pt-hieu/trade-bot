-- Migration 285: Fix remaining phantom tool references (post-282)
--
-- Check 1: Remove phantom entries from enabled_tools arrays (5 agents)
-- Check 2: Rewrite prompt text for tool_* refs not in enabled_tools (16 agents)
--
-- Usage: uv run python scripts/db/run_migration.py 285_fix_remaining_phantom_tools.sql
-- Prod:  SWINGY_ENV=production uv run python scripts/db/run_migration.py 285_fix_remaining_phantom_tools.sql

-- ============================================================================
-- CHECK 1: Remove phantom tools from enabled_tools arrays
-- ============================================================================

-- position_strategist: remove tool_get_holdings (not in registry)
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_holdings')
WHERE agent_key = 'position_strategist'
  AND 'tool_get_holdings' = ANY(enabled_tools);

-- positions: remove tool_get_holdings
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_holdings')
WHERE agent_key = 'positions'
  AND 'tool_get_holdings' = ANY(enabled_tools);

-- trading_mode: remove tool_get_holdings
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_holdings')
WHERE agent_key = 'trading_mode'
  AND 'tool_get_holdings' = ANY(enabled_tools);

-- sector_technical: remove tool_get_my_beliefs
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_my_beliefs')
WHERE agent_key = 'sector_technical'
  AND 'tool_get_my_beliefs' = ANY(enabled_tools);

-- refiner: remove tool_get_cash, tool_get_holdings, tool_list_articles
UPDATE agent_prompts
SET enabled_tools = array_remove(array_remove(array_remove(enabled_tools, 'tool_get_cash'), 'tool_get_holdings'), 'tool_list_articles')
WHERE agent_key = 'refiner'
  AND ('tool_get_cash' = ANY(enabled_tools) OR 'tool_get_holdings' = ANY(enabled_tools) OR 'tool_list_articles' = ANY(enabled_tools));

-- ============================================================================
-- CHECK 2: Rewrite prompt text — tool_get_my_beliefs (6 agents)
-- ============================================================================

-- sector_news
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before analyzing each ticker, retrieve your prior beliefs via tool_get_my_beliefs.',
    'Your prior beliefs are pre-loaded in context above.'
)
WHERE agent_key = 'sector_news'
  AND system_prompt LIKE '%tool_get_my_beliefs%';

-- positions_value
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before analyzing each ticker, retrieve your prior beliefs via tool_get_my_beliefs.',
    'Your prior beliefs are pre-loaded in context above.'
)
WHERE agent_key = 'positions_value'
  AND system_prompt LIKE '%tool_get_my_beliefs%';

-- positions_technical
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before analyzing each ticker, retrieve your prior beliefs via tool_get_my_beliefs.',
    'Your prior beliefs are pre-loaded in context above.'
)
WHERE agent_key = 'positions_technical'
  AND system_prompt LIKE '%tool_get_my_beliefs%';

-- positions_thesis
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before analyzing each ticker, retrieve your prior beliefs via tool_get_my_beliefs.',
    'Your prior beliefs are pre-loaded in context above.'
)
WHERE agent_key = 'positions_thesis'
  AND system_prompt LIKE '%tool_get_my_beliefs%';

-- sector_enrichment
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before analyzing each ticker, retrieve your prior beliefs via tool_get_my_beliefs.',
    'Your prior beliefs are pre-loaded in context above.'
)
WHERE agent_key = 'sector_enrichment'
  AND system_prompt LIKE '%tool_get_my_beliefs%';

-- sector_technical (already removed from enabled_tools, now fix prompt)
-- No prompt ref for tool_get_my_beliefs in sector_technical (it was only in enabled_tools)

-- ============================================================================
-- CHECK 2: Rewrite prompt text — tool_get_belief_accuracy (6 agents)
-- ============================================================================

-- sector_news
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Check your accuracy via tool_get_belief_accuracy before finalizing',
    '- Check the belief accuracy data pre-loaded in context above before finalizing'
)
WHERE agent_key = 'sector_news'
  AND system_prompt LIKE '%tool_get_belief_accuracy%';

-- positions_value
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Check tool_get_belief_accuracy. Base rates: 35/40/25.',
    '- Check belief accuracy data pre-loaded above. Base rates: 35/40/25.'
)
WHERE agent_key = 'positions_value'
  AND system_prompt LIKE '%tool_get_belief_accuracy%';

-- positions_aggregator
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before finalizing beliefs, call tool_get_belief_accuracy(perspective="all") to see all agents'' track records.',
    'Before finalizing beliefs, review the belief accuracy data pre-loaded in context above to see all agents'' track records.'
)
WHERE agent_key = 'positions_aggregator'
  AND system_prompt LIKE '%tool_get_belief_accuracy%';

-- sector_aggregator
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before finalizing beliefs, call tool_get_belief_accuracy(perspective="all") to see all agents'' track records.',
    'Before finalizing beliefs, review the belief accuracy data pre-loaded in context above to see all agents'' track records.'
)
WHERE agent_key = 'sector_aggregator'
  AND system_prompt LIKE '%tool_get_belief_accuracy%';

-- sector_enrichment
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Check your accuracy via tool_get_belief_accuracy before finalizing',
    '- Check the belief accuracy data pre-loaded in context above before finalizing'
)
WHERE agent_key = 'sector_enrichment'
  AND system_prompt LIKE '%tool_get_belief_accuracy%';

-- ============================================================================
-- CHECK 2: Rewrite prompt text — tool_get_holdings (2 agents: positions_technical, positions_thesis)
-- ============================================================================

-- positions_technical
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- tool_get_holdings(): Portfolio positions with P/L, weight, plan_type',
    '- Holdings data (pre-loaded above): Portfolio positions with P/L, weight, plan_type'
)
WHERE agent_key = 'positions_technical'
  AND system_prompt LIKE '%tool_get_holdings(): Portfolio%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- DO NOT assume positions not returned by tool_get_holdings exist',
    '- DO NOT assume positions not in the pre-loaded holdings data exist'
)
WHERE agent_key = 'positions_technical'
  AND system_prompt LIKE '%not returned by tool_get_holdings%';

-- positions_thesis
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- tool_get_holdings(): Portfolio positions with P/L, weight, plan_type',
    '- Holdings data (pre-loaded above): Portfolio positions with P/L, weight, plan_type'
)
WHERE agent_key = 'positions_thesis'
  AND system_prompt LIKE '%tool_get_holdings(): Portfolio%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- DO NOT assume positions not returned by tool_get_holdings exist',
    '- DO NOT assume positions not in the pre-loaded holdings data exist'
)
WHERE agent_key = 'positions_thesis'
  AND system_prompt LIKE '%not returned by tool_get_holdings%';

-- ============================================================================
-- CHECK 2: Rewrite prompt text — tool_get_technicals (1 agent: positions_technical)
-- ============================================================================

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- tool_get_technicals(ticker): RSI, MACD, MA, ATR, Supertrend, BBands, Stochastic, volume context',
    '- Technical data (pre-loaded above): RSI, MACD, MA, ATR, Supertrend, BBands, Stochastic, volume context'
)
WHERE agent_key = 'positions_technical'
  AND system_prompt LIKE '%tool_get_technicals(ticker): RSI%';

-- ============================================================================
-- CHECK 2: Rewrite prompt text — tool_search_news (1 agent: positions_thesis)
-- ============================================================================

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- tool_search_news(query): Recent news and catalyst developments',
    '- tool_search_articles(query): Recent news and catalyst developments'
)
WHERE agent_key = 'positions_thesis'
  AND system_prompt LIKE '%tool_search_news(query)%';

-- ============================================================================
-- CHECK 2: Rewrite prompt text — sector_technical phantoms
-- ============================================================================

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- tool_get_ticker_data: Get price levels, RSI, MACD, volume, ATR, pattern data',
    '- Technical data (pre-loaded above): price levels, RSI, MACD, volume, ATR, pattern data'
)
WHERE agent_key = 'sector_technical'
  AND system_prompt LIKE '%tool_get_ticker_data: Get price%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- DO NOT compute your own R:R ratios — use tool_calculate_trade_setup instead',
    '- DO NOT compute your own R:R ratios — trade setups are pre-computed in context above'
)
WHERE agent_key = 'sector_technical'
  AND system_prompt LIKE '%use tool_calculate_trade_setup instead%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- DO NOT recommend trades where tool_calculate_trade_setup returns valid=False',
    '- DO NOT recommend trades where the pre-computed trade setup shows valid=False'
)
WHERE agent_key = 'sector_technical'
  AND system_prompt LIKE '%tool_calculate_trade_setup returns valid%';

-- ============================================================================
-- CHECK 2: Rewrite prompt text — entry_strategist: tool_list_articles
-- ============================================================================

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '9. tool_list_articles(sector=X) — browse today''s articles for a sector',
    '9. tool_search_articles(query=X) — browse today''s articles for a sector'
)
WHERE agent_key = 'entry_strategist'
  AND system_prompt LIKE '%tool_list_articles(sector=X)%';

-- ============================================================================
-- CHECK 2: Rewrite prompt text — market_level (4 phantom refs)
-- ============================================================================

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '1. tool_get_vnindex() - Get VN-Index technicals (RSI, Stochastic, Bollinger, support/resistance)',
    '1. VN-Index technicals (pre-loaded above) — RSI, Stochastic, Bollinger, support/resistance'
)
WHERE agent_key = 'market_level'
  AND system_prompt LIKE '%tool_get_vnindex()%Get VN-Index%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'If tool_get_vnindex returns empty or error:',
    'If VN-Index data in context is empty or missing:'
)
WHERE agent_key = 'market_level'
  AND system_prompt LIKE '%If tool_get_vnindex returns%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '2. tool_get_rotation() - Get hot/cold sector rotation data',
    '2. Sector rotation data (pre-loaded above) — hot/cold sectors'
)
WHERE agent_key = 'market_level'
  AND system_prompt LIKE '%tool_get_rotation()%Get hot/cold%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '3. tool_get_history() - Get recent regime history for trend analysis',
    '3. Regime history (pre-loaded above) — recent trend analysis data'
)
WHERE agent_key = 'market_level'
  AND system_prompt LIKE '%tool_get_history()%Get recent regime%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '4. tool_search_news(query) - Search for market news and catalysts',
    '4. tool_search_articles(query) - Search for market news and catalysts'
)
WHERE agent_key = 'market_level'
  AND system_prompt LIKE '%tool_search_news(query)%Search for market%';

-- ============================================================================
-- CHECK 2: Rewrite prompt text — catalysts: tool_get_current_catalysts
-- ============================================================================

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- catalyst_id: ID from tool_get_current_catalysts()',
    '- catalyst_id: ID from the catalyst data pre-loaded in context'
)
WHERE agent_key = 'catalysts'
  AND system_prompt LIKE '%tool_get_current_catalysts()%';

-- ============================================================================
-- ROUND 2: Remaining phantoms after first pass
-- ============================================================================

-- positions: tool_get_holdings in prompt text (3 refs)
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- tool_get_holdings() returns {"holdings": {...}, "prose": "Portfolio Holdings: XYZ: 100 shares..."}',
    '- Holdings data (pre-loaded above) format: {"holdings": {...}, "prose": "Portfolio Holdings: XYZ: 100 shares..."}'
)
WHERE agent_key = 'positions'
  AND system_prompt LIKE '%tool_get_holdings() returns%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '1. tool_get_holdings() - Get portfolio positions with P/L, weight, plan_type',
    '1. Holdings data (pre-loaded above) — portfolio positions with P/L, weight, plan_type'
)
WHERE agent_key = 'positions'
  AND system_prompt LIKE '%1. tool_get_holdings() - Get portfolio%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '1. Get all holdings via tool_get_holdings',
    '1. Review all holdings from the pre-loaded data above'
)
WHERE agent_key = 'positions'
  AND system_prompt LIKE '%Get all holdings via tool_get_holdings%';

-- sector_technical: tool_get_my_beliefs in prompt text
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before analyzing each ticker, retrieve your prior beliefs via tool_get_my_beliefs.',
    'Your prior beliefs are pre-loaded in context above.'
)
WHERE agent_key = 'sector_technical'
  AND system_prompt LIKE '%tool_get_my_beliefs%';
