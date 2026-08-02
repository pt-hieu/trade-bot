-- Migration 170: Set max_tokens for watchlist_sector_evaluator
--
-- Sector evaluator had max_tokens = null, falling back to Together AI
-- default of 2048. Financial sector (17 tickers) could not fit structured
-- output in 2048 tokens, causing 3 retries then failure.
-- Migration 114 only covered heavy tier agents. This one was classified light.

UPDATE agent_prompts
SET max_tokens = 20000
WHERE agent_key = 'watchlist_sector_evaluator';
