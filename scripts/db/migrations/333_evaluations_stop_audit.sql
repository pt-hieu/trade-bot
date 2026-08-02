-- Migration 333: persist `stop_price_vnd` (the stop the evaluator checked
-- against) on every retro evaluation row.
--
-- Phase 2 §2.1 — audit-trail evidence for stop_hit decisions. Today the
-- stop level lives only on `daily_recommendations`, so re-deriving the
-- exact stop the evaluator used (in the presence of catastrophic / trail
-- migrations to the recs row) requires a join AND a guess at temporal
-- ordering. Persisting it on the eval row turns audit into a single
-- SELECT.
--
-- Migration is intentionally 2-step:
--   Step A (this file): add NULLABLE column + CHECK so future writes
--     populate it. Backfill from daily_recommendations.stop_price_vnd
--     for past rows. The check fires only when value is NOT NULL so
--     legacy MISSED rows (no stop) pass.
--   Step B (later, gated on 100% backfill): NULL → NOT NULL via a
--     follow-up migration. Held back from this migration so any
--     mid-deploy retro between Python rollout + this SQL doesn't
--     fail-loud on legacy rows.

ALTER TABLE daily_evaluations
    ADD COLUMN IF NOT EXISTS stop_price_vnd integer;

ALTER TABLE daily_evaluations
    DROP CONSTRAINT IF EXISTS daily_evaluations_stop_price_vnd_check;

ALTER TABLE daily_evaluations
    ADD CONSTRAINT daily_evaluations_stop_price_vnd_check
    CHECK (stop_price_vnd IS NULL OR stop_price_vnd >= 1000);

-- Backfill from the rec row when the eval row is missing the column.
-- Joins on (record_id, ticker, recommendation) — the same composite key
-- the rec → eval pipeline uses.
UPDATE daily_evaluations e
SET stop_price_vnd = r.stop_price_vnd
FROM daily_recommendations r
WHERE e.record_id = r.record_id
  AND e.ticker = r.ticker
  AND e.recommendation = r.action
  AND e.stop_price_vnd IS NULL
  AND r.stop_price_vnd IS NOT NULL
  AND r.stop_price_vnd >= 1000;
