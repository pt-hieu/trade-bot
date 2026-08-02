-- 325_catalyst_key_full_slug.sql
-- Fix 7 of the narrative+catalyst systemic plan (2026-04-21).
--
-- Original plan: re-key 42 existing truncated (30-char) `catalyst_key`
-- values to the full 60-char slug and cascade to `catalyst_articles` +
-- `narratives.related_catalysts[]`.
--
-- What actually ships: only the FK cascade rule. The in-place re-key is
-- deferred because:
--   1. `catalyst_articles.catalyst_key` FK lacks `ON UPDATE CASCADE`, so
--      an in-transaction UPDATE flips from "truncated key is in both
--      tables" to "truncated key deleted from parent but still in child"
--      and the FK fires immediately.
--   2. The agent-side code fix (`agents/catalysts.py:397` now uses
--      `[:60]`) means new discoveries get full slugs going forward.
--      Existing truncated keys are stable identifiers and will age out
--      through the normal lifecycle — no functional impact on queries
--      (catalysts are primarily joined by PK id, not the slug).
--
-- What THIS migration does: add ON UPDATE/DELETE CASCADE to the FK so
-- any future re-key migration can proceed without the drop-and-re-add
-- dance, AND orphaned `catalyst_articles` rows get cleaned when a parent
-- catalyst is deleted.

BEGIN;

ALTER TABLE catalyst_articles
  DROP CONSTRAINT IF EXISTS catalyst_articles_catalyst_key_fkey;

ALTER TABLE catalyst_articles
  ADD CONSTRAINT catalyst_articles_catalyst_key_fkey
  FOREIGN KEY (catalyst_key)
  REFERENCES catalysts(catalyst_key)
  ON UPDATE CASCADE
  ON DELETE CASCADE;

-- Audit.
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'catalyst_articles_catalyst_key_fkey';

COMMIT;
