-- Migration 204: Add calibration fields to daily_evaluations
-- Type: DDL (requires owner connection)
--
-- These fields are computed in-memory by retro/compute.py and retro/calibration.py
-- but were never persisted, breaking the rolling window calibration feedback loop.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/204_eval_calibration_columns.sql

ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS entry_gap_pct DECIMAL(8,2);
ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS predicted_rr DECIMAL(8,2);
ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS actual_max_rr DECIMAL(8,2);
ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS stop_buffer_pct DECIMAL(8,2);
ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS stop_vs_atr_ratio DECIMAL(8,2);
ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS atr_pct DECIMAL(8,2);
