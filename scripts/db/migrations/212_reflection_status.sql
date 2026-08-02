-- Migration 212: Add reflection_status to daily_records
-- Type: DDL (requires owner connection)
--
-- Track whether morning brief was reviewed by critic/refiner loop.
-- Values: 'reviewed', 'skipped_timeout', 'skipped_error', NULL (legacy/unknown)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/212_reflection_status.sql

ALTER TABLE daily_records ADD COLUMN IF NOT EXISTS reflection_status VARCHAR(20) DEFAULT NULL;
