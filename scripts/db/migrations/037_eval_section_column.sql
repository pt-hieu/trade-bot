-- 037: Add section column to daily_evaluations to prevent cross-product JOINs
--
-- Problem: When a ticker (e.g., VHM) appears in multiple sections (MY_HOLDINGS + WHAT_TO_DO),
-- the LEFT JOIN on (record_id, ticker) creates a cross product with daily_evaluations.
-- Fix: Add section column so JOIN can match on (record_id, ticker, section).

ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS section TEXT;

-- Backfill today's data based on recommendation action mapping
-- HOLD/TRIM/EXIT evals → MY_HOLDINGS section
-- WATCH/BUY/LIMIT_BUY evals in WHAT_TO_DO or by matching daily_recommendations
UPDATE daily_evaluations ev
SET section = rec.section
FROM daily_recommendations rec
WHERE ev.record_id = rec.record_id
  AND ev.ticker = rec.ticker
  AND ev.recommendation::text = rec.action::text
  AND ev.section IS NULL;

-- For remaining unmatched evals, try matching by (record_id, ticker) where there's only one rec
UPDATE daily_evaluations ev
SET section = (
    SELECT rec.section FROM daily_recommendations rec
    WHERE rec.record_id = ev.record_id AND rec.ticker = ev.ticker
    LIMIT 1
)
WHERE ev.section IS NULL;
