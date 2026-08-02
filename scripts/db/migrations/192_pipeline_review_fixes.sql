-- Migration 192: Pipeline review fixes (2026-03-19)
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Fixes from morning brief pipeline review:
-- 1. Bump max_tokens from 20000 to 96000 for ALL active agents (critic was truncating at 20K)
-- 2. Set temperature = 0.2 for analytical agents with NULL temperature
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/192_pipeline_review_fixes.sql

-- 1. max_tokens → 96000 for ALL active agents
UPDATE agent_prompts
SET max_tokens = 96000, updated_at = NOW()
WHERE is_active = true;

-- 2. Analytical agents: NULL temperature → 0.2
UPDATE agent_prompts
SET temperature = 0.2, updated_at = NOW()
WHERE agent_key IN (
    'macro_interpreter',
    'news_examiner',
    'capital_events',
    'catalysts',
    'retro_commentary',
    'retro_generator',
    'positions_pev_verifier'
) AND temperature IS NULL;
