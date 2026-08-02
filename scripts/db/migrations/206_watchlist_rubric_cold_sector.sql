-- Migration 206: Add cold sector penalty to watchlist addition criteria
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Root cause: Sector evaluator rubric had asymmetric scoring —
-- cold sector gave +20 for removal but no penalty for addition.
-- Adding -15 (not -20) because cold sector should be a headwind, not a blocker.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/206_watchlist_rubric_cold_sector.sql

UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- Has upcoming catalyst: +10 points',
    '- Has upcoming catalyst: +10 points
- In cold sector: -15 points'
),
    updated_at = NOW()
WHERE agent_key = 'watchlist_sector_evaluator'
  AND system_prompt LIKE '%Has upcoming catalyst: +10 points%'
  AND system_prompt NOT LIKE '%In cold sector: -15 points%';
