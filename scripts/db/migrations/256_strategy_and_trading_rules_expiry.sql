-- Migration 256: Add strategy to daily_evaluations + trading_rules expiry cleanup
--
-- Fixes:
-- 1. daily_evaluations missing strategy column — retro pattern extractor can never
--    compute per-strategy win rates (strategy_insights table permanently empty)
-- 2. trading_rules.expires_at always NULL — stale rules persist forever
-- 3. Expire old stale trading_rules that were created by buggy code (pre-Feb 23 fix)

-- 1. Add strategy column to daily_evaluations
ALTER TABLE daily_evaluations
  ADD COLUMN IF NOT EXISTS strategy VARCHAR(20);

-- 2. Set default expires_at for trading_rules (30 days from last_validated or created_at)
UPDATE trading_rules
SET expires_at = COALESCE(last_validated, created_at::date) + INTERVAL '30 days'
WHERE expires_at IS NULL;

-- 3. Add default for future trading_rules rows
ALTER TABLE trading_rules
  ALTER COLUMN expires_at SET DEFAULT CURRENT_DATE + INTERVAL '30 days';
