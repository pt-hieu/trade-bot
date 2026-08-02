-- Migration 309: Add match_method column to catalyst_news_signals
-- Type: DDL (requires owner connection)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/309_catalyst_match_method.sql

ALTER TABLE catalyst_news_signals
    ADD COLUMN IF NOT EXISTS match_method VARCHAR(20) DEFAULT 'keyword';
