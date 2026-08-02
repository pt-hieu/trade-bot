-- Migration 230: Backfill won for HOLD rows with day_change + fix PENDING
--
-- Source of truth: scripts/agents/retro/won.py:compute_won()
-- Thresholds: HOLD+TRIM/EXIT → day_change >= 0, HOLD+other → day_change >= -1.0
-- Run AFTER backfill_day_change.py populates day_change values.

-- HOLD + TRIM/EXIT action → won if day_change >= 0
UPDATE daily_evaluations
SET won = (day_change >= 0)
WHERE status = 'HOLD'
  AND won IS NULL
  AND day_change IS NOT NULL
  AND recommendation IN ('TRIM', 'EXIT');

-- HOLD + other action → won if day_change >= -1.0
UPDATE daily_evaluations
SET won = (day_change >= -1.0)
WHERE status = 'HOLD'
  AND won IS NULL
  AND day_change IS NOT NULL
  AND recommendation NOT IN ('TRIM', 'EXIT');

-- PENDING → won = NULL (not scoreable, matches compute_won() after PENDING fix)
UPDATE daily_evaluations
SET won = NULL
WHERE status = 'PENDING'
  AND won IS NOT NULL;
