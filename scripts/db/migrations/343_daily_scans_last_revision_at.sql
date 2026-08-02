-- SWI-275: idempotent intraday spike detection.
-- Track when the most recent strategy revision (or clean no-spike inspection)
-- consumed the catalyst state for a scan_date, so subsequent same-day cron
-- runs use GREATEST(created_at, last_revision_at) as their predicate baseline
-- and stop re-firing on the same catalysts.

ALTER TABLE daily_scans
    ADD COLUMN IF NOT EXISTS last_revision_at TIMESTAMPTZ NULL;

COMMENT ON COLUMN daily_scans.last_revision_at IS
    'Timestamp of the last successful run_strategy_revision (or clean no-spike '
    'inspection) for this scan_date. Used by detect_catalyst_spike to make '
    'spike detection idempotent across same-day cron runs (SWI-275).';
