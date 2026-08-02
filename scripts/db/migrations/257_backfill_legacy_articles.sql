-- Migration 257: Backfill legacy articles with NULL published_at and domain
-- Type: Data (no DDL)
--
-- 731 articles (inserted Mar 3-24) have NULL published_at — the field was
-- added later and the insert code now has a fallback to scan_date.
-- 433 articles have NULL domain — same era, domain extraction was added later.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/257_backfill_legacy_articles.sql

-- Backfill published_at from created_at where NULL
UPDATE articles SET published_at = created_at WHERE published_at IS NULL;

-- Backfill domain from URL where NULL
UPDATE articles
SET domain = REGEXP_REPLACE(REGEXP_REPLACE(url, '^https?://(www\.)?', ''), '/.*$', '')
WHERE domain IS NULL AND url IS NOT NULL AND url != '';
