-- Migration 282: Fix ALL remaining phantom tool refs across 12 agents
--
-- Comprehensive scan found 12 agents with tool_* references not in enabled_tools.
-- SWINGY_TOOL_STRICT=1 raises ValueError on these, crashing the pipeline.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py 282_fix_all_phantom_tool_refs.sql

-- === bear_reviewer: tool_get_belief_accuracy (not in enabled_tools=[]) ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Use tool_get_belief_accuracy to check your own track record and calibrate confidence accordingly.',
    'Review the belief accuracy data pre-loaded in context above to check your own track record and calibrate confidence accordingly.'
)
WHERE agent_key = 'bear_reviewer'
  AND system_prompt LIKE '%tool_get_belief_accuracy%';

-- === bull_reviewer: tool_get_belief_accuracy (not in enabled_tools=[]) ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Use tool_get_belief_accuracy to check your own track record and calibrate confidence accordingly.',
    'Review the belief accuracy data pre-loaded in context above to check your own track record and calibrate confidence accordingly.'
)
WHERE agent_key = 'bull_reviewer'
  AND system_prompt LIKE '%tool_get_belief_accuracy%';

-- === positions_thesis: tool_get_belief_accuracy (negative ref triggers regex) ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Calibration data is pre-loaded in context above (do NOT call tool_get_belief_accuracy)',
    '- Calibration data is pre-loaded in context above — no tool calls needed'
)
WHERE agent_key = 'positions_thesis'
  AND system_prompt LIKE '%tool_get_belief_accuracy%';

-- === entry_strategist: tool_get_learnings, tool_get_similar_days ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Call tool_get_learnings(query="calibration") before writing entry recommendations.',
    'Review the calibration data pre-loaded in context above before writing entry recommendations.'
)
WHERE agent_key = 'entry_strategist'
  AND system_prompt LIKE '%Call tool_get_learnings(query="calibration")%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before applying calibration overrides from tool_get_learnings(query="calibration"):',
    'Before applying calibration overrides from the pre-loaded calibration data:'
)
WHERE agent_key = 'entry_strategist'
  AND system_prompt LIKE '%overrides from tool_get_learnings%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'When citing historical win rates from tool_get_similar_days output:',
    'When citing historical win rates from the similar-days data in context above:'
)
WHERE agent_key = 'entry_strategist'
  AND system_prompt LIKE '%tool_get_similar_days%';

-- === midday: tool_get_learnings, tool_get_midday_prices, tool_get_trades ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Call tool_get_learnings(query="midday_insights") before making recommendation overrides.',
    'Review the midday insights pre-loaded in context above before making recommendation overrides.'
)
WHERE agent_key = 'midday'
  AND system_prompt LIKE '%tool_get_learnings(query="midday_insights")%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Use actual midday prices from tool_get_midday_prices(), not invented values.',
    'Use actual midday prices from the data pre-loaded in context above, not invented values.'
)
WHERE agent_key = 'midday'
  AND system_prompt LIKE '%tool_get_midday_prices()%not invented%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'If tool_get_midday_prices returns empty, error, or stale prices:',
    'If midday prices in context are empty or stale:'
)
WHERE agent_key = 'midday'
  AND system_prompt LIKE '%If tool_get_midday_prices returns%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'uses actual midday prices from tool_get_midday_prices',
    'uses actual midday prices from the pre-loaded data'
)
WHERE agent_key = 'midday'
  AND system_prompt LIKE '%uses actual midday prices from tool_get_midday_prices%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Call tool_get_trades to confirm. Do NOT recommend actions on positions that no longer exist.',
    'Check the trades data pre-loaded in context above. Do NOT recommend actions on positions that no longer exist.'
)
WHERE agent_key = 'midday'
  AND system_prompt LIKE '%Call tool_get_trades to confirm%';

-- === positions: tool_search_news (should be tool_search_articles) ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '4. tool_search_news(query) - Search for breaking news about a stock',
    '4. tool_search_articles(query) - Search for breaking news about a stock'
)
WHERE agent_key = 'positions'
  AND system_prompt LIKE '%tool_search_news%';

-- === refiner: tool_get_articles, tool_get_capital, tool_get_cash, tool_get_holdings, tool_get_technicals ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '3. tool_get_articles() -- Get today''s news headlines if NEWS section missing',
    '3. Today''s news headlines are pre-loaded in context above'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%tool_get_articles()%Get today%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- NEWS THAT MATTERS: Use tool_get_articles() to get today''s headlines',
    '- NEWS THAT MATTERS: Use the pre-loaded news headlines from context above'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%NEWS THAT MATTERS: Use tool_get_articles%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- GOAL PROGRESS: Use tool_get_capital() to get goal data',
    '- GOAL PROGRESS: Use the goal data pre-loaded in context above'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%tool_get_capital()%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '2. tool_get_cash() -- Check actual deployable cash',
    '2. Deployable cash data is pre-loaded in context above'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%2. tool_get_cash()%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Use tool_get_cash() to get actual deployable cash',
    '- Use the deployable cash data pre-loaded in context above'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%Use tool_get_cash() to get actual%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- CAPITAL STATUS: Use tool_get_cash() to add cash/reserve info',
    '- CAPITAL STATUS: Use the cash/reserve data pre-loaded in context above'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%CAPITAL STATUS: Use tool_get_cash%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '1. tool_get_holdings() -- Verify portfolio tickers and P/L',
    '1. Portfolio tickers and P/L are pre-loaded in context above'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%1. tool_get_holdings()%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Use tool_get_holdings() to verify portfolio state',
    '- Verify portfolio state using the holdings data pre-loaded in context above'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%Use tool_get_holdings() to verify%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Use tool_get_holdings() to get actual portfolio tickers',
    '- Use the holdings data pre-loaded in context above for actual portfolio tickers'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%Use tool_get_holdings() to get actual%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Do NOT recalculate using tool_get_technicals.',
    'Do NOT recalculate using tools.'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%recalculate using tool_get_technicals%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Use tool_get_technicals(ticker) to get real levels',
    '- Use the technical levels pre-loaded in context above'
)
WHERE agent_key = 'refiner'
  AND system_prompt LIKE '%Use tool_get_technicals(ticker) to get real%';

-- === sector: tool_get_ticker_data, tool_list_articles ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'tool_get_ticker_data(ticker) - Get price, RSI, MACD, MA data for any ticker',
    'Ticker data (price, RSI, MACD, MA) is pre-loaded in context for each ticker'
)
WHERE agent_key = 'sector'
  AND system_prompt LIKE '%tool_get_ticker_data(ticker) - Get price%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'First, use tool_get_ticker_data for each ticker to get current technicals',
    'First, review the pre-loaded ticker data for each ticker to get current technicals'
)
WHERE agent_key = 'sector'
  AND system_prompt LIKE '%use tool_get_ticker_data for each%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'tool_get_ticker_data returns pre-computed pattern and trend analysis:',
    'The pre-loaded ticker data includes pre-computed pattern and trend analysis:'
)
WHERE agent_key = 'sector'
  AND system_prompt LIKE '%tool_get_ticker_data returns pre-computed%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'tool_get_ticker_data includes a "price_action" section when recent price shows unusual moves.',
    'The pre-loaded ticker data includes a "price_action" section when recent price shows unusual moves.'
)
WHERE agent_key = 'sector'
  AND system_prompt LIKE '%tool_get_ticker_data includes a "price_action"%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'If tool_get_ticker_data returns empty, error, or stale data (scan_date != today) for a ticker:',
    'If the pre-loaded ticker data is empty or stale (scan_date != today) for a ticker:'
)
WHERE agent_key = 'sector'
  AND system_prompt LIKE '%If tool_get_ticker_data returns empty%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'you MUST call tool_get_ticker_data(ticker) AND tool_get_valuation_history(ticker)',
    'you MUST review the pre-loaded ticker data AND call tool_get_valuation_history(ticker)'
)
WHERE agent_key = 'sector'
  AND system_prompt LIKE '%MUST call tool_get_ticker_data%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'tool_list_articles(sector) - List available news articles for a sector',
    'tool_search_articles(query) - Search news articles for a sector'
)
WHERE agent_key = 'sector'
  AND system_prompt LIKE '%tool_list_articles(sector)%';

-- === sector_rotation: tool_get_learnings ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Historical rotation data is available via tool_get_learnings',
    'Historical rotation data is pre-loaded in context above'
)
WHERE agent_key = 'sector_rotation'
  AND system_prompt LIKE '%available via tool_get_learnings%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Before scoring sectors, call tool_get_learnings(query="rotation_patterns") to check your historical accuracy.',
    'Before scoring sectors, review the rotation accuracy data pre-loaded in context above.'
)
WHERE agent_key = 'sector_rotation'
  AND system_prompt LIKE '%call tool_get_learnings(query="rotation_patterns")%';

-- === strategy_director: all tools are context-injected ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '1. tool_get_holdings() — for POSITION GUIDANCE',
    '1. Holdings data (pre-loaded above) — for POSITION GUIDANCE'
)
WHERE agent_key = 'strategy_director'
  AND system_prompt LIKE '%1. tool_get_holdings()%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- NEVER use breakeven_stop from tool_get_holdings() when pre-computed stops are available.',
    '- NEVER use breakeven_stop from holdings data when pre-computed stops are available.'
)
WHERE agent_key = 'strategy_director'
  AND system_prompt LIKE '%breakeven_stop from tool_get_holdings%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '3. tool_get_learnings(query="summary") — for win rate context',
    '3. Learnings data (pre-loaded above) — for win rate context'
)
WHERE agent_key = 'strategy_director'
  AND system_prompt LIKE '%3. tool_get_learnings%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '2. tool_get_trades() — for MINDSET (recent W/L)',
    '2. Recent trades (pre-loaded above) — for MINDSET (recent W/L)'
)
WHERE agent_key = 'strategy_director'
  AND system_prompt LIKE '%2. tool_get_trades()%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '7. tool_losing_patterns(regime=X) — for KEY RISK',
    '7. Losing patterns (pre-loaded above) — for KEY RISK'
)
WHERE agent_key = 'strategy_director'
  AND system_prompt LIKE '%7. tool_losing_patterns%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '4. tool_similar_days(regime=X, hot_sectors=Y, macro=Z) — for MARKET MOOD',
    '4. Similar days data (pre-loaded above) — for MARKET MOOD'
)
WHERE agent_key = 'strategy_director'
  AND system_prompt LIKE '%4. tool_similar_days%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '5. tool_trading_rules(regime=X, sectors=Y) — for KEY RISK',
    '5. Trading rules (pre-loaded above) — for KEY RISK'
)
WHERE agent_key = 'strategy_director'
  AND system_prompt LIKE '%5. tool_trading_rules%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '6. tool_winning_patterns(regime=X) — to validate stance',
    '6. Winning patterns (pre-loaded above) — to validate stance'
)
WHERE agent_key = 'strategy_director'
  AND system_prompt LIKE '%6. tool_winning_patterns%';

-- === synthesis: all tools are context-injected ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '5. tool_calculate_trade_setup() — Calculate Entry/Stop/Target/R:R from levels',
    '5. Trade setups (Entry/Stop/Target/R:R) are pre-computed in context above'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%5. tool_calculate_trade_setup()%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Do NOT re-call tool_calculate_trade_setup for pre-computed picks',
    '- Do NOT recalculate trade setups for pre-computed picks'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%re-call tool_calculate_trade_setup%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '1. MY HOLDINGS — from tool_get_holdings() + POSITION GUIDANCE',
    '1. MY HOLDINGS — from pre-loaded holdings data + POSITION GUIDANCE'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%MY HOLDINGS — from tool_get_holdings%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '1. tool_get_holdings() — Current positions with P/L data',
    '1. Holdings data (pre-loaded above) — Current positions with P/L data'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%1. tool_get_holdings() — Current%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- ONLY tickers from tool_get_holdings()',
    '- ONLY tickers from the pre-loaded holdings data'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%ONLY tickers from tool_get_holdings%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'If tool_get_holdings returns empty or error: write "INSUFFICIENT DATA — holdings unavailable" for MY HOLDINGS section.',
    'If holdings data in context is empty: write "INSUFFICIENT DATA — holdings unavailable" for MY HOLDINGS section.'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%If tool_get_holdings returns empty%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '3. TOP PICKS — from pre-computed candidates + tool_get_stats()',
    '3. TOP PICKS — from pre-computed candidates + statistical data in context'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%TOP PICKS — from pre-computed candidates + tool_get_stats%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '4. tool_get_stats() — Statistical probability data from historical patterns',
    '4. Statistical data (pre-loaded above) — Probability data from historical patterns'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%4. tool_get_stats()%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Use tool_get_stats() to make quantitative probability statements:',
    'Use the pre-loaded statistical data to make quantitative probability statements:'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%Use tool_get_stats() to make%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '2. tool_get_trades() — Recent trade history',
    '2. Recent trades (pre-loaded above) — Recent trade history'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%2. tool_get_trades() — Recent%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '3. tool_position_scale() — Position sizing multiplier based on win rate',
    '3. Position sizing multiplier (pre-loaded above) — Based on win rate'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%3. tool_position_scale()%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'CALL tool_position_scale() before calculating position sizes.',
    'Use the pre-loaded position sizing multiplier before calculating position sizes.'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%CALL tool_position_scale()%';

-- === watchlist_update: tool_get_technicals -> tool_watchlist_technicals, tool_search_news -> tool_watchlist_search_news ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '2. tool_get_technicals(ticker) - Get RSI, MACD, MA for any stock (fetches real-time if not cached)',
    '2. tool_watchlist_technicals(ticker) - Get RSI, MACD, MA for any stock (fetches real-time if not cached)'
)
WHERE agent_key = 'watchlist_update'
  AND system_prompt LIKE '%2. tool_get_technicals(ticker)%';

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '3. tool_search_news(query) - Search week''s news articles',
    '3. tool_watchlist_search_news(query) - Search week''s news articles'
)
WHERE agent_key = 'watchlist_update'
  AND system_prompt LIKE '%3. tool_search_news(query)%';

-- === synthesis: last phantom in example text ===
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    'Entry must come from tool_calculate_trade_setup.',
    'Entry must come from the pre-computed trade setup.'
)
WHERE agent_key = 'synthesis'
  AND system_prompt LIKE '%Entry must come from tool_calculate_trade_setup%';
