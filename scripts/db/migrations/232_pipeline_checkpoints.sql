-- Migration 232: Pipeline checkpoints for Phase 2 resume
-- Type: DDL (requires owner connection)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/232_pipeline_checkpoints.sql

CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_date DATE NOT NULL,
    phase VARCHAR(50) NOT NULL,
    schema_version INT NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(scan_date, phase)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_checkpoints_scan_date
    ON pipeline_checkpoints(scan_date);
