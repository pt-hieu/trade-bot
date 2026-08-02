-- Migration 304: Tombstone stale beliefs that fell outside the 60-day scoring window.
-- Sets outcome_date to their computed horizon and marks actual_direction as 'EXPIRED'
-- to distinguish from properly scored beliefs (which have brier_score IS NOT NULL).
-- This is a safety net — the self-healing logic in resolve_mature_beliefs() will
-- tombstone future stale beliefs automatically during each retro run.

UPDATE agent_beliefs
SET outcome_date = record_date + timeframe_days * INTERVAL '1 day',
    actual_direction = 'EXPIRED'
WHERE outcome_date IS NULL
  AND record_date + timeframe_days * INTERVAL '1 day' < CURRENT_DATE - INTERVAL '60 days';
