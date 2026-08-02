-- Migration 063: Add expires_at to trading_rules for rule lifecycle management
-- Rules expire 14 days after last_validated by default

ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS expires_at DATE;

-- Back-fill expiry for existing rows based on last_validated
UPDATE trading_rules
SET expires_at = last_validated + INTERVAL '14 days'
WHERE expires_at IS NULL
  AND last_validated IS NOT NULL;

-- Rows with no last_validated get a 14-day window from today
UPDATE trading_rules
SET expires_at = CURRENT_DATE + INTERVAL '14 days'
WHERE expires_at IS NULL;

-- Index for efficient non-expired rule queries
CREATE INDEX IF NOT EXISTS idx_trading_rules_expires_at ON trading_rules(expires_at);
