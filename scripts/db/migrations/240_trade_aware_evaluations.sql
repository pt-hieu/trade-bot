-- Migration 240: Add trade execution tracking to daily_evaluations
-- Type: DDL (requires owner connection)
--
-- Context: Retro pipeline evaluates HOLD/TRIM/EXIT recs against EOD prices only.
-- When user actually executes a trade (e.g., TRIM → sold at 103k for +12.96%),
-- the retro has no awareness and incorrectly evaluates as "HOLD".
-- These columns track actual trade execution alongside theoretical evaluation.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/240_trade_aware_evaluations.sql

ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS trade_executed BOOLEAN DEFAULT FALSE;
ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS actual_exit_price_vnd BIGINT;
ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS actual_pl_pct NUMERIC(8,4);
ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS actual_pl_net_vnd BIGINT;
