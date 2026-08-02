-- Migration 271: Longterm review pipeline fixes
-- Type: Data (default DATABASE_URL works)
--
-- A. Fix sector misclassifications: GAS, MWG, SSI in longterm_watchlist
-- B. Remove unused tools from longterm_review agent
-- C. Append concentration risk instruction to longterm_review system prompt
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/271_longterm_review_fixes.sql

-- ── A. Fix sector misclassifications ──────────────────────────────────────────

-- GAS (PetroVietnam Gas): consumer -> state_owned
UPDATE longterm_watchlist
SET sector_id = (SELECT id FROM sectors WHERE name = 'state_owned'),
    updated_at = NOW()
WHERE ticker = 'GAS'
  AND sector_id = (SELECT id FROM sectors WHERE name = 'consumer');

-- MWG (Mobile World): technology -> consumer
UPDATE longterm_watchlist
SET sector_id = (SELECT id FROM sectors WHERE name = 'consumer'),
    updated_at = NOW()
WHERE ticker = 'MWG'
  AND sector_id = (SELECT id FROM sectors WHERE name = 'technology');

-- SSI (SSI Securities): technology -> securities
UPDATE longterm_watchlist
SET sector_id = (SELECT id FROM sectors WHERE name = 'securities'),
    updated_at = NOW()
WHERE ticker = 'SSI'
  AND sector_id = (SELECT id FROM sectors WHERE name = 'technology');

-- ── B. Remove unused tools from longterm_review ─────────────────────────────

UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_watchlist'),
    updated_at = NOW()
WHERE agent_key = 'longterm_review'
  AND 'tool_get_watchlist' = ANY(enabled_tools);

UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_financial_health'),
    updated_at = NOW()
WHERE agent_key = 'longterm_review'
  AND 'tool_get_financial_health' = ANY(enabled_tools);

UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_comps'),
    updated_at = NOW()
WHERE agent_key = 'longterm_review'
  AND 'tool_get_comps' = ANY(enabled_tools);

-- ── C. Append concentration risk check to system prompt ──────────────────────

UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONCENTRATION RISK CHECK\nIf any single sector exceeds 40% of the watchlist, flag it as a concentration risk in market_outlook. Do NOT recommend additions in sectors exceeding 40%. Prefer additions in the most underweight sector to improve diversification.',
    updated_at = NOW()
WHERE agent_key = 'longterm_review';
