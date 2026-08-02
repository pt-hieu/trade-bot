-- Migration 292: Widen catalyst impact column and drop strict CHECK constraint
-- Fixes: "value too long for type character varying(20)" in news pipeline (2026-04-07)
-- Root cause: LLM agent produces values outside the enumerated set (e.g. "SLIGHTLY_POSITIVE")
-- Fix: widen column + drop CHECK so pipeline doesn't fail on unexpected values.
-- The catalysts.py agent already validates output. DB shouldn't double-gate LLM text.

-- Drop existing check constraint and widen column
ALTER TABLE catalysts DROP CONSTRAINT IF EXISTS catalysts_impact_check;
ALTER TABLE catalysts ALTER COLUMN impact TYPE VARCHAR(50);

-- Also widen actual_impact (same pattern, varchar(20))
ALTER TABLE catalysts DROP CONSTRAINT IF EXISTS catalysts_actual_impact_check;
ALTER TABLE catalysts ALTER COLUMN actual_impact TYPE VARCHAR(50);

-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/292_widen_catalyst_impact.sql
