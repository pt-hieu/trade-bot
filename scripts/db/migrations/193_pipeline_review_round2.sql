-- Migration 193: Set temperatures for remaining agents + critic max_tokens cap
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Fixes from pipeline review 2026-03-19:
-- 1. Set temperature for 20 analytical agents still at NULL (provider default ~1.0)
-- 2. Set sector_news temperature to 0.3 (needs some creativity for news interpretation)
-- 3. Reduce critic max_tokens from 96000 to 20000 (cap explosion while allowing 10K-15K legitimate critiques)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/193_pipeline_review_round2.sql

-- Analytical/deterministic agents: temperature 0.2
UPDATE agent_prompts
SET temperature = 0.2, updated_at = NOW()
WHERE agent_key IN (
    'critic', 'refiner',
    'synthesis_picks', 'synthesis_holdings',
    'entry_strategist', 'market_level',
    'position_strategist', 'midday',
    'retro_evaluator', 'trading_mode',
    'sector_technical', 'sector_enrichment',
    'positions_technical', 'positions',
    'positions_value', 'positions_thesis',
    'positions_pev_alert', 'longterm',
    'sector_rotation', 'alert_analyst'
) AND temperature IS NULL;

-- sector_news: slight creativity for news interpretation
UPDATE agent_prompts
SET temperature = 0.3, updated_at = NOW()
WHERE agent_key = 'sector_news' AND temperature IS NULL;

-- Critic: reduce max_tokens to prevent output explosion (33K tokens in round 3)
UPDATE agent_prompts
SET max_tokens = 20000, updated_at = NOW()
WHERE agent_key = 'critic';
