-- Migration 225: Backfill won field in daily_evaluations
--
-- won was never set by compute.py (only set in-memory by update_learnings).
-- Now compute_won() sets it before DB write. This backfills historical rows.
-- Uses same logic as compute_won() in scripts/agents/retro/won.py.

-- WIN status → won=true
UPDATE daily_evaluations SET won = true
WHERE status = 'WIN' AND won IS NULL;

-- LOSS status → won=false
UPDATE daily_evaluations SET won = false
WHERE status = 'LOSS' AND won IS NULL;

-- STOP_BREACHED → won=false
UPDATE daily_evaluations SET won = false
WHERE status = 'STOP_BREACHED' AND won IS NULL;

-- HOLD (non TRIM/EXIT): won if day_change >= -1.0
UPDATE daily_evaluations SET won = true
WHERE status = 'HOLD' AND won IS NULL
  AND recommendation NOT IN ('TRIM', 'EXIT')
  AND day_change IS NOT NULL AND day_change >= -1.0;

UPDATE daily_evaluations SET won = false
WHERE status = 'HOLD' AND won IS NULL
  AND recommendation NOT IN ('TRIM', 'EXIT')
  AND day_change IS NOT NULL AND day_change < -1.0;

-- HOLD TRIM/EXIT: won if day_change >= 0
UPDATE daily_evaluations SET won = true
WHERE status = 'HOLD' AND won IS NULL
  AND recommendation IN ('TRIM', 'EXIT')
  AND day_change IS NOT NULL AND day_change >= 0;

UPDATE daily_evaluations SET won = false
WHERE status = 'HOLD' AND won IS NULL
  AND recommendation IN ('TRIM', 'EXIT')
  AND day_change IS NOT NULL AND day_change < 0;

-- EXCLUDED, MISSED, PENDING without day_change → stay NULL (not scoreable)
