-- Migration 182: Fix null model_id + standardize max_tokens.
-- Pipeline review 2026-03-13: synthesis failed because 7 agents had NULL model_id.
-- entry_strategist hit max_tokens overflow, critic hit implicit 4096 cap.

-- 1. Fix null model_id for 7 agents that caused synthesis failure
UPDATE agent_prompts SET model_id = 'moonshotai/Kimi-K2.5', updated_at = NOW()
WHERE agent_key IN (
  'sector_technical', 'sector_enrichment', 'sector_aggregator',
  'sector_news', 'retro_commentary', 'synthesis_holdings', 'synthesis_picks'
) AND model_id IS NULL;

-- 2. Set max_tokens = 20000 for all active agents with NULL or lower
UPDATE agent_prompts SET max_tokens = 20000, updated_at = NOW()
WHERE is_active = true AND (max_tokens IS NULL OR max_tokens < 20000);
