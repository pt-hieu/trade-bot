-- Migration 228: Fix SKIP/AVOID/WAIT/WATCH recs with wrong status
--
-- ~31 rows from Jan-Feb 2026 have recommendation IN ('SKIP','AVOID') but status='WIN'.
-- These predate EXCLUDED_ACTIONS enforcement. Fix: set status=EXCLUDED, won=NULL.

UPDATE daily_evaluations
SET status = 'EXCLUDED', won = NULL
WHERE recommendation IN ('SKIP', 'AVOID', 'WAIT', 'WATCH')
  AND status != 'EXCLUDED';
