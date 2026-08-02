-- Migration 250: Prevent duplicate (narrative_id, article_id) in narrative_updates
-- Type: DDL (requires owner connection)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/250_narrative_updates_unique.sql

-- Delete duplicates keeping the row with the lowest id (earliest insert)
DELETE FROM narrative_updates a
USING narrative_updates b
WHERE a.narrative_id = b.narrative_id
  AND a.article_id = b.article_id
  AND a.id > b.id;

ALTER TABLE narrative_updates
    ADD CONSTRAINT uq_narrative_article UNIQUE (narrative_id, article_id);
