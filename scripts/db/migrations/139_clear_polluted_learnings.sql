-- Migration 139: Clear polluted learnings data
-- Purges hallucinated patterns (n=49/38) from pre-migration-049 LLM extractor
-- and stale summary from Feb 13 when update_learnings() wasn't being called.
-- Backfill script (scripts/backfill_learnings.py) repopulates from daily_records DB.
-- Idempotency: DELETE on empty tables is a no-op.

DELETE FROM learning_patterns;
DELETE FROM learnings_summary;
