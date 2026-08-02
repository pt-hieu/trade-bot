-- Migration 280: Agent prompt audit — inject-instead-of-tool + phantom + silent cleanup
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Audit found 3 defect classes:
-- 1. Tools that prompts prescribe calling, but data is deterministic/known → convert to injection
-- 2. Phantom/stale tool references in system prompts
-- 3. Silent tools (enabled but undocumented in prompts) → remove
--
-- Usage: uv run python scripts/db/run_migration.py 280_inject_audit_cleanup.sql

-- ══════════════════════════════════════════════════════════════════════════
-- STEP 1: Update enabled_tools (declarative target per agent)
-- ══════════════════════════════════════════════════════════════════════════

UPDATE agent_prompts SET enabled_tools = '{tool_search_articles,tool_read_article,tool_get_active_narratives}'
WHERE agent_key = 'entry_strategist';

UPDATE agent_prompts SET enabled_tools = '{tool_search_articles}'
WHERE agent_key = 'market_level';

UPDATE agent_prompts SET enabled_tools = '{tool_search_sector_news}'
WHERE agent_key = 'sector_rotation';

UPDATE agent_prompts SET enabled_tools = '{tool_get_technicals}'
WHERE agent_key = 'midday';

UPDATE agent_prompts SET enabled_tools = '{}'
WHERE agent_key IN ('bear_reviewer', 'bull_reviewer', 'positions_technical', 'synthesis_holdings');

UPDATE agent_prompts SET enabled_tools = '{tool_get_longterm_config,tool_search_articles,tool_get_active_narratives}'
WHERE agent_key = 'positions_thesis';

UPDATE agent_prompts SET enabled_tools = '{tool_get_valuation,tool_get_longterm_config,tool_get_valuation_history,tool_get_earnings_quality}'
WHERE agent_key = 'positions_value';

UPDATE agent_prompts SET enabled_tools = '{tool_get_valuation_history,tool_get_block_trades}'
WHERE agent_key = 'sector_enrichment';

UPDATE agent_prompts SET enabled_tools = '{tool_search_articles,tool_read_article,tool_get_learnings,tool_get_active_narratives}'
WHERE agent_key = 'sector_news';

UPDATE agent_prompts SET enabled_tools = '{tool_position_scale,tool_calculate_trade_setup,tool_get_relative_strength,tool_get_stats}'
WHERE agent_key = 'synthesis_picks';

-- Clean dead/deactivated agents
UPDATE agent_prompts SET enabled_tools = '{}'
WHERE agent_key IN ('strategy_director', 'synthesis');

-- ══════════════════════════════════════════════════════════════════════════
-- STEP 2: Update system_prompt text (tool refs → pre-loaded headers)
-- ══════════════════════════════════════════════════════════════════════════

-- entry_strategist: update tool usage section
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$## Tool Usage
1. tool_get_trades() — for MINDSET (recent W/L count)
2. tool_get_learnings(query="summary") — for win rate context
3. tool_get_learnings(query="calibration") — for CALIBRATION SELF-CHECK (see below)
4. tool_get_similar_days(regime=X, hot_sectors=Y, macro=Z) — for MARKET MOOD
5. tool_trading_rules(regime=X, sectors=Y) — for KEY RISK
6. tool_winning_patterns(regime=X) — to validate stance
7. tool_losing_patterns(regime=X) — for KEY RISK
8. tool_get_retro_constraints() — check if entry limits are reduced by poor performance$$,
    $$## Data Sources
All data for MINDSET, MARKET MOOD, KEY RISK, and CALIBRATION is pre-loaded in context above.
- Recent trades, learnings (summary + calibration), similar days, trading rules,
  winning/losing patterns, and retro constraints are ALL injected — do NOT call tools for these.
- Use tool_search_articles or tool_read_article for deeper news investigation if needed.
- Use tool_get_active_narratives for market narrative context if needed.$$
) WHERE agent_key = 'entry_strategist';

-- market_level: update steps referencing tools
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$2. tool_get_rotation() — Get hot/cold sector rotation data
3. tool_get_learnings(query) — Get regime accuracy history for self-calibration$$,
    $$2. Sector rotation data is pre-loaded in context above
3. Regime accuracy history is pre-loaded in context above$$
) WHERE agent_key = 'market_level';

-- sector_rotation: update tool list
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$1. tool_get_sector_data() - Get RSI and price data for all stocks by sector$$,
    $$1. Sector RSI and price data is pre-loaded in context above$$
) WHERE agent_key = 'sector_rotation';

-- midday: update tool instructions (5 replacements)
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$4. tool_get_midday_prices() - Get ACTUAL midday OHLCV prices at market break
5. tool_get_trades() - Get recent trades (check if positions were exited/entered today)$$,
    $$4. Midday OHLCV prices are pre-loaded in context above
5. Recent trades are pre-loaded in context above$$
) WHERE agent_key = 'midday';

UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$Use tool_get_midday_prices() for intraday data (open, high, low, close at midday)$$,
    $$Use the midday prices pre-loaded in context above for intraday data$$
) WHERE agent_key = 'midday';

UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$Call tool_get_executed_trades() to identify positions OPENED OR CLOSED TODAY$$,
    $$Review the executed trades pre-loaded in context above for positions OPENED OR CLOSED TODAY$$
) WHERE agent_key = 'midday';

UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$Call tool_get_trades to get recent trade history for context$$,
    $$Review the recent trade history pre-loaded in context above$$
) WHERE agent_key = 'midday';

UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$Call tool_get_midday_prices for today's intraday data$$,
    $$Review midday prices pre-loaded in context above$$
) WHERE agent_key = 'midday';

-- positions_technical: remove "Your only tool" section
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$Your only tool:
- tool_get_belief_accuracy(): Check your past belief accuracy for calibration$$,
    $$Your calibration data is pre-loaded in context above (do NOT call tool_get_belief_accuracy).$$
) WHERE agent_key = 'positions_technical';

UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$- Check tool_get_belief_accuracy. Base rates: 35/40/25.$$,
    $$- Check the calibration data above. Base rates: 35/40/25.$$
) WHERE agent_key = 'positions_technical';

-- positions_thesis: remove belief_accuracy from tool list
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$- tool_get_belief_accuracy(): Check your past belief accuracy for calibration$$,
    $$- Calibration data is pre-loaded in context above (do NOT call tool_get_belief_accuracy)$$
) WHERE agent_key = 'positions_thesis';

UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$- Check tool_get_belief_accuracy. Base rates: 35/40/25.$$,
    $$- Check the calibration data above. Base rates: 35/40/25.$$
) WHERE agent_key = 'positions_thesis';

-- sector_enrichment: add calibration reference
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$If your past Brier > 0.5, anchor harder to base rates$$,
    $$Check the calibration data pre-loaded above. If your past Brier > 0.5, anchor harder to base rates$$
) WHERE agent_key = 'sector_enrichment';

-- sector_news: add calibration reference
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$If your past Brier > 0.5, anchor harder to base rates$$,
    $$Check the calibration data pre-loaded above. If your past Brier > 0.5, anchor harder to base rates$$
) WHERE agent_key = 'sector_news';

-- synthesis_holdings: update tool list
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$- tool_get_trades: Get recent trade history for context$$,
    $$- Recent trade history is pre-loaded in context above$$
) WHERE agent_key = 'synthesis_holdings';

-- longterm_review: document tool_read_research
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$- Use tool_get_valuation for quantitative data, tool_search_articles for recent news$$,
    $$- Use tool_get_valuation for quantitative data, tool_search_articles for recent news
- Use tool_read_research(ticker) to access existing research notes for context$$
) WHERE agent_key = 'longterm_review';

-- longterm: batch tool hints
UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$tool_get_technicals(ticker) - Get current price, RSI, MACD, trend for a ticker$$,
    $$tool_get_technicals(tickers) - Get current price, RSI, MACD, trend (pass list like ['FPT','TCB'])$$
) WHERE agent_key = 'longterm';

UPDATE agent_prompts SET system_prompt = REPLACE(
    system_prompt,
    $$tool_get_longterm_config(ticker) - Get entry zone, conviction, and zone status for a ticker$$,
    $$tool_get_longterm_config(tickers) - Get entry zone, conviction, zone status (pass list like ['FPT','TCB'])$$
) WHERE agent_key = 'longterm';
