-- Migration 310: Add EVALUATE to rec_action enum
-- Type: DDL (requires owner connection)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/310_add_evaluate_to_rec_action.sql
--
-- Context: EVALUATE has been a valid position action in the pipeline since migration 033
-- but was never added to the rec_action DB enum. This caused execute_many to fail
-- silently when any recommendation had action=EVALUATE, dropping ALL recs for that day.
-- Affected: Apr 13-16 2026 (0 recommendations persisted despite 3-5 buy signals/day).

ALTER TYPE rec_action ADD VALUE IF NOT EXISTS 'EVALUATE';
