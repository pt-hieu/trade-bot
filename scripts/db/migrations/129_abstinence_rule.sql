-- Migration 129: Add INSUFFICIENT DATA RULE (abstinence) to 7 agents
--
-- Adds to:
--   sector:          WAIT signal when tool data missing/empty
--   synthesis:       Empty section with explanation when holdings/picks unavailable
--   midday:          Cannot assess when midday prices unavailable
--   longterm:        WAIT status when technicals/entry zone missing
--   watchlist_update: Skip stock when technicals unavailable
--   market_level:    NEUTRAL + low confidence when VN-Index data missing
--   positions:       Low urgency when technicals empty/incomplete
--
-- Also bumps sector output_retries from 0 to 1 (needed for Literal type validation retry)
--
-- All UPDATEs are idempotent: guarded by NOT LIKE '%INSUFFICIENT DATA RULE%'

-- 1. sector: Abstinence when ticker data is missing
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## INSUFFICIENT DATA RULE\nIf tool_get_ticker_data returns empty, error, or stale data (scan_date != today) for a ticker:\n- Set signal to "WAIT" with note: "INSUFFICIENT DATA — [what is missing, e.g. technicals unavailable]"\n- Do NOT infer prices, RSI values, patterns, or support/resistance levels from memory or other tickers.\n- Do NOT retry with invented data.\n- A WAIT signal with honest reasoning is better than a BUY signal built on absent data.\nApplies to: price comparisons, RSI readings, pattern identifications, support/resistance levels.'
WHERE agent_key = 'sector'
AND system_prompt NOT LIKE '%INSUFFICIENT DATA RULE%';

-- 2. synthesis: Abstinence when holdings or pick pipeline data is missing
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## INSUFFICIENT DATA RULE\nBeyond the LOW_CASH/REALLOCATION mode handling already defined:\n- If pre_computed_picks is entirely absent (not empty, but not provided): write "INSUFFICIENT DATA — pick pipeline did not run" in the TOP PICKS section.\n- If tool_get_holdings returns empty or error: write "INSUFFICIENT DATA — holdings unavailable" for MY HOLDINGS section.\n- Do NOT invent holdings or picks from memory when tools return no data.\nAn empty section with an honest explanation is better than a fabricated one.'
WHERE agent_key = 'synthesis'
AND system_prompt NOT LIKE '%INSUFFICIENT DATA RULE%';

-- 3. midday: Abstinence when midday prices are unavailable
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## INSUFFICIENT DATA RULE\nIf tool_get_midday_prices returns empty, error, or stale prices:\n- Set morning_reflection: "INSUFFICIENT DATA — midday prices unavailable for [tickers]"\n- Set afternoon_plan: "Defer to original morning plan until prices available"\n- Do NOT fabricate intraday performance, estimate from yesterday''s close, or extrapolate from related tickers.\nA midday review with an honest data gap is better than one with invented prices.'
WHERE agent_key = 'midday'
AND system_prompt NOT LIKE '%INSUFFICIENT DATA RULE%';

-- 4. longterm: Abstinence when price/entry zone/technicals data is missing
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## INSUFFICIENT DATA RULE\nIf tool_get_technicals returns empty or current price is zero/unavailable for a ticker:\n- Set status to "WAIT" with action: "INSUFFICIENT DATA — [what is missing, e.g. technicals unavailable]"\n- Do NOT estimate entry zone gap, RSI level, or trend direction from memory or other tickers.\n- A WAIT with an honest data gap is better than a false BUY ZONE signal.\nApplies to: current price, entry zone gap, RSI, trend direction, conviction level.'
WHERE agent_key = 'longterm'
AND system_prompt NOT LIKE '%INSUFFICIENT DATA RULE%';

-- 5. watchlist_update: Abstinence when technicals unavailable for a stock
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## INSUFFICIENT DATA RULE\nIf tool_watchlist_technicals returns empty or error for a stock:\n- Do NOT score that stock for addition or removal.\n- Skip it entirely with note: "INSUFFICIENT DATA — technicals unavailable"\n- Never invent RSI values, sector assignments, or trend direction to fill gaps.\nA watchlist update that honestly skips 3 stocks is better than one that scores them on invented data.'
WHERE agent_key = 'watchlist_update'
AND system_prompt NOT LIKE '%INSUFFICIENT DATA RULE%';

-- 6. market_level: Abstinence when VN-Index or source data is insufficient
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## INSUFFICIENT DATA RULE\nIf tool_get_vnindex returns empty or error:\n- Set regime to "NEUTRAL" with regime_confidence 0.3\n- Set key_signal: "INSUFFICIENT DATA — VN-Index technicals unavailable"\n- Do NOT classify regime from memory or news sentiment alone.\nIf fewer than 3 independent indicator sources are available: set regime_confidence <= 0.5 and explicitly note which sources are missing.'
WHERE agent_key = 'market_level'
AND system_prompt NOT LIKE '%INSUFFICIENT DATA RULE%';

-- 7. positions: Abstinence when holding technicals are incomplete
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## INSUFFICIENT DATA RULE\nIf tool_get_technicals returns empty or incomplete for a holding:\n- Set urgency to "low" with reason: "INSUFFICIENT DATA — technicals unavailable for [ticker]"\n- Do NOT fabricate RSI values, support levels, or trend direction.\n- Pre-computed trailing stops still apply and should be cited even without fresh technicals.\nA "monitor" alert noting a data gap is better than an EXIT recommendation based on invented signals.'
WHERE agent_key = 'positions'
AND system_prompt NOT LIKE '%INSUFFICIENT DATA RULE%';

-- 8. sector: Bump output_retries to 1 (needed for Literal type validation retry)
UPDATE agent_prompts
SET output_retries = 1
WHERE agent_key = 'sector'
AND output_retries = 0;
