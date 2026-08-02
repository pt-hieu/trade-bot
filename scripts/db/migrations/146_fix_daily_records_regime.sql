-- Migration 146: Backfill daily_records.market_regime from market_regimes table
--
-- daily_records.market_regime was NULL for most rows because:
-- 1. retrospective.py's insert_daily_record() had `market_regime = EXCLUDED.market_regime`
--    which overwrote the morning's value with NULL (retro data dict lacked market_regime).
--    Fixed in insert_records.py to use COALESCE.
-- 2. Some rows were created before the morning brief consistently wrote market_regime.
--
-- This migration fills in NULLs by joining with market_regimes (source of truth).

UPDATE daily_records dr
SET market_regime = mr.regime
FROM market_regimes mr
WHERE dr.record_date = mr.scan_date
  AND dr.market_regime IS NULL;
