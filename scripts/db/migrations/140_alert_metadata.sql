-- Migration 140: Add alert_metadata JSONB column to alerts table
-- Supports multi-tranche dip-buy setups with setup_id linking tranches

ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_metadata JSONB DEFAULT '{}';

-- Partial index for setup_id lookups (tranche sibling queries)
CREATE INDEX IF NOT EXISTS idx_alerts_setup_id
  ON alerts ((alert_metadata->>'setup_id'))
  WHERE alert_metadata->>'setup_id' IS NOT NULL;
