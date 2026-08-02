-- Migration 184: Tune watchlist agent configs
--
-- 1. Set explicit temperature for deterministic scoring (was NULL = provider default ~0.7-1.0)
-- 2. Reduce coordinator max_tokens from 20000 to 4000 (actual output ~1600 tokens)

UPDATE agent_prompts
SET temperature = 0.3
WHERE agent_key = 'watchlist_sector_evaluator'
  AND temperature IS NULL;

UPDATE agent_prompts
SET temperature = 0.3
WHERE agent_key = 'watchlist_coordinator'
  AND temperature IS NULL;
