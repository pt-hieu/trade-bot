-- Migration 249: Article URL deduplication
-- Type: DDL (requires owner connection)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/249_article_url_dedup.sql

-- Unique constraint for UPSERT in insert_articles (replaces DELETE+INSERT)
ALTER TABLE articles
    ADD CONSTRAINT uq_articles_url_search UNIQUE (url, search_id);

-- Deduplicated article view: when same URL appears in multiple searches,
-- prefer the most recent search (highest scan_date).
CREATE OR REPLACE VIEW articles_deduped AS
SELECT DISTINCT ON (url)
    a.*
FROM articles a
JOIN article_searches ars ON ars.id = a.search_id
ORDER BY url, ars.scan_date DESC, a.created_at DESC;
