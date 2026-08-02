-- Migration 066: Add recommendation_overrides JSONB to midday_checks
-- Stores structured per-ticker midday status vs morning recommendation

ALTER TABLE midday_checks
  ADD COLUMN IF NOT EXISTS recommendation_overrides JSONB DEFAULT '[]';

-- Comment for documentation
COMMENT ON COLUMN midday_checks.recommendation_overrides IS
  'Structured per-ticker midday status: [{ticker, morning_action, midday_status, reason, revised_entry, revised_stop, revised_target}]';
