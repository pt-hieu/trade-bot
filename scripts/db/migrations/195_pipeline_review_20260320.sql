-- Migration 195: Pipeline review fixes (2026-03-20)
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Fixes from pipeline review 2026-03-20:
-- 1. Critic: add cross-section conflict checker to review checklist
-- 2. synthesis_picks: add SKIP vs BUY coherence rule to prevent same ticker in both sections
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/195_pipeline_review_20260320.sql

-- 1. Critic: cross-section conflict check
UPDATE agent_prompts
SET system_prompt = system_prompt || '

## CROSS-SECTION CONFLICT CHECK (MANDATORY)
Verify no ticker appears in both an actionable section (BUY/WATCH/HOLD in TOP PICKS or LONG-TERM) AND SKIP THESE.
If found: flag as CRITICAL issue. The SKIP reasoning must win unless the BUY thesis explicitly addresses and overrides every skip concern.
A ticker cannot simultaneously be recommended for purchase and flagged for avoidance.',
    updated_at = NOW()
WHERE agent_key = 'critic'
  AND system_prompt NOT LIKE '%CROSS-SECTION CONFLICT%';

-- 2. synthesis_picks: SKIP vs BUY coherence
UPDATE agent_prompts
SET system_prompt = system_prompt || '

## SKIP THESE vs BUY COHERENCE (MANDATORY)
Before finalizing your output:
1. Review every ticker you placed in TOP PICKS
2. Check if the same ticker appears in your SKIP THESE with insider/flow concerns
3. If yes: REMOVE from TOP PICKS — insider/institutional exit vetoes technical entry
Never recommend BUY when coordinated insider selling (CEO/CFO/BOD) is documented in sector analysis.
A ticker MUST NOT appear in both TOP PICKS and SKIP THESE.',
    updated_at = NOW()
WHERE agent_key = 'synthesis_picks'
  AND system_prompt NOT LIKE '%SKIP THESE vs BUY COHERENCE%';
