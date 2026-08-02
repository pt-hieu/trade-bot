-- Migration 266: Add partial unique index on alerts to prevent duplicates
-- Root cause: application-level dedup (snapshot-based) has race conditions.
-- Index includes `source` to allow morning + midday alerts for same ticker.

-- Step 1: Remove existing active duplicates (keep lowest id per group)
DELETE FROM alerts a
WHERE a.status = 'active'
AND EXISTS (
    SELECT 1 FROM alerts b
    WHERE b.ticker = a.ticker
      AND b.recommended_action = a.recommended_action
      AND b.source_date = a.source_date
      AND b.source = a.source
      AND b.status = 'active'
      AND b.id < a.id
);

-- Step 2: Create partial unique index (only enforced for active alerts)
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_active_dedup
    ON alerts (ticker, recommended_action, source_date, source)
    WHERE status = 'active';
