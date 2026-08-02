-- Migration 258: Clean junk narratives and dead single-article narratives
-- Type: DML (safe on read-only connection)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py 258_clean_junk_narratives.sql

-- 1. Unlink articles from junk narratives before deleting
UPDATE articles SET narrative_id = NULL
WHERE narrative_id IN (
    SELECT id FROM narratives
    WHERE LOWER(theme) LIKE '%lacks content%'
       OR LOWER(theme) LIKE '%no specific theme%'
       OR LOWER(theme) LIKE '%daily market summary%'
);

-- 2. Delete narrative_updates for junk narratives
DELETE FROM narrative_updates
WHERE narrative_id IN (
    SELECT id FROM narratives
    WHERE LOWER(theme) LIKE '%lacks content%'
       OR LOWER(theme) LIKE '%no specific theme%'
       OR LOWER(theme) LIKE '%daily market summary%'
);

-- 3. Delete junk narratives
DELETE FROM narratives
WHERE LOWER(theme) LIKE '%lacks content%'
   OR LOWER(theme) LIKE '%no specific theme%'
   OR LOWER(theme) LIKE '%daily market summary%';

-- 4. Mark dead single-article narratives as stale (conviction < 0.10, older than 3 days)
UPDATE narratives
SET status = 'stale', updated_at = NOW()
WHERE status = 'active'
  AND article_count <= 1
  AND conviction_score < 0.10
  AND first_seen < CURRENT_DATE - INTERVAL '3 days';
