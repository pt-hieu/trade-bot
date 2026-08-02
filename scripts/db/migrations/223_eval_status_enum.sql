-- Migration 223: Add EXCLUDED and STOP_BREACHED to eval_status enum
--
-- compute.py produces these statuses but they were missing from the enum.
-- EXCLUDED was silently converted to PENDING by Python allowlist (data loss).
-- STOP_BREACHED was in Python allowlist but would crash on DB insert.
--
-- NOTE: ALTER TYPE ADD VALUE cannot run inside a transaction.
-- run_migration.py runs each statement individually (autocommit) — safe.

ALTER TYPE eval_status ADD VALUE IF NOT EXISTS 'EXCLUDED';

ALTER TYPE eval_status ADD VALUE IF NOT EXISTS 'STOP_BREACHED';
