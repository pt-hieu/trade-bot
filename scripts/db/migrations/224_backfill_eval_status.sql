-- Migration 224: Backfill eval_status for EXCLUDED and STOP_BREACHED
--
-- Previously, EXCLUDED status was silently converted to PENDING by Python allowlist.
-- WATCH/WAIT/SKIP/AVOID recommendations should have status=EXCLUDED, not PENDING.
-- HOLD with stop_hit=true should be STOP_BREACHED, not HOLD.

-- Fix WATCH/WAIT/SKIP/AVOID that were mangled to PENDING
UPDATE daily_evaluations
SET status = 'EXCLUDED'
WHERE status = 'PENDING'
  AND recommendation IN ('WATCH', 'WAIT', 'SKIP', 'AVOID');

-- Fix HOLD with stop_hit=true that should be STOP_BREACHED
UPDATE daily_evaluations
SET status = 'STOP_BREACHED'
WHERE status = 'HOLD'
  AND stop_hit = true;
