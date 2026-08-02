-- Migration 207: Fix SAB sector misclassification
-- Type: Data (default DATABASE_URL works)
--
-- SAB (Sabeco) is a consumer/beverage company but swing_watchlist has it
-- mapped to infrastructure sector. Fix to consumer.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/207_fix_sab_sector.sql

UPDATE swing_watchlist
SET sector_id = (SELECT id FROM sectors WHERE name = 'consumer'),
    updated_at = NOW()
WHERE ticker = 'SAB'
  AND sector_id != (SELECT id FROM sectors WHERE name = 'consumer');
