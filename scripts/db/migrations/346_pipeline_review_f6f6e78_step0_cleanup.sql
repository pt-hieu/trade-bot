-- SWI-125: Step 0 cleanup for pipeline-review f6f6e7828c8d (2026-05-12).
--
-- Removes the May 12 SAB BUY recommendation that was persisted in thousand-VND
-- units (entry_price_vnd=44 instead of ~44000) due to nearest_swing_low /
-- nearest_swing_target missing from analysis._PRICE_LEVEL_KEYS (added by
-- SWI-289 commit 5cee1c5e but not propagated to the normalizer allowlist).
-- The row anchors the zero-BUY streak detector incorrectly; deleting it lets
-- the streak walk-back at retro/streak.py treat May 12 as a true zero-BUY day.
--
-- Also purges legacy capital_events rows whose ticker is empty / NULL / 'UNK'
-- so the May-13 brief catalyst-summaries renderer stops shipping malformed
-- rows like ": ipo 2026 (du kien) (?)". Producer-side guard is Cutover G.
--
-- Audit (2026-05-13) confirmed:
--   * 1 row in daily_recommendations matches the SAB unit-leak predicate.
--   * 1 row in capital_events matches the empty-ticker predicate (id=6,
--     event_key='_ipo_2026', from 2026-02-26).
--   * refiner_overrides has 0 SAB rows for 2026-05-12 — no override delete.
--   * alerts.id=326 is already 'cancelled' — no status update.
--
-- All predicates are doubly-narrowed and idempotent (re-running this migration
-- is a no-op).

BEGIN;

-- 1. Remove the unit-leak SAB BUY row from daily_recommendations.
--    Predicate (entry_price_vnd < 1000) doubly-narrows so a healthy SAB BUY
--    persisted in the future is never touched.
DELETE FROM daily_recommendations
 WHERE ticker = 'SAB'
   AND action = 'BUY'
   AND record_id = (SELECT id FROM daily_records WHERE record_date = '2026-05-12')
   AND entry_price_vnd < 1000;

-- 2. Recompute daily_records.buy_rec_count from surviving rec rows.
--    Same-transaction read-after-write returns 0 for 2026-05-12 once the
--    SAB row is gone — streak detector then treats today as zero-BUY.
UPDATE daily_records dr
   SET buy_rec_count = (
       SELECT COUNT(*)
         FROM daily_recommendations
        WHERE record_id = dr.id
          AND action = 'BUY'
   )
 WHERE record_date = '2026-05-12';

-- 3. Purge malformed capital_events rows (empty / NULL / 'UNK' / whitespace
--    ticker). Bundled here because the cleanup window is the same; Cutover G
--    adds the producer-side Pydantic guard so these don't regenerate.
DELETE FROM capital_events
 WHERE ticker IS NULL
    OR ticker = ''
    OR ticker = 'UNK'
    OR TRIM(ticker) = '';

INSERT INTO schema_migrations (version)
VALUES ('346_pipeline_review_f6f6e78_step0_cleanup')
ON CONFLICT DO NOTHING;

COMMIT;
