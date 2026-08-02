-- Migration 094: Clean stale catalyst data + add tracking columns
-- Date: 2026-02-22

-- Mark Tet holiday as completed (ended Feb 22, 2026)
UPDATE catalysts
SET status = 'completed',
    outcome = 'Tet holiday 2026 concluded. Market reopened Feb 22.',
    actual_date = '2026-02-22',
    updated_at = NOW()
WHERE catalyst_key = 'tet_holiday_2026'
  AND status = 'active';

-- Add discovery_source column to catalysts
ALTER TABLE catalysts
    ADD COLUMN IF NOT EXISTS discovery_source VARCHAR(50);

-- Add last_checked column to catalysts
ALTER TABLE catalysts
    ADD COLUMN IF NOT EXISTS last_checked TIMESTAMPTZ;

-- Backfill discovery_source for existing rows
UPDATE catalysts
SET discovery_source = 'seed_048'
WHERE discovery_source IS NULL;

-- Add discovery_source column to capital_events
ALTER TABLE capital_events
    ADD COLUMN IF NOT EXISTS discovery_source VARCHAR(50);

-- Add last_checked column to capital_events
ALTER TABLE capital_events
    ADD COLUMN IF NOT EXISTS last_checked TIMESTAMPTZ;

-- Backfill discovery_source for existing rows
UPDATE capital_events
SET discovery_source = 'seed_048'
WHERE discovery_source IS NULL;
