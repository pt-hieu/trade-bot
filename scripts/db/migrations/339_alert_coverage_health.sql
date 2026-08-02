-- Migration 339: Persist coverage health (responding, total) on each
-- morning_position_alerts row so cross-retry preserve_higher_urgency
-- can prefer the higher-coverage attempt over the more-confident-but-
-- degraded earlier attempt (SWI-183).
--
-- NULL on either column = row predates this migration; merge rule
-- treats NULL pair as "unknown" and falls through to action-rank only
-- (skips COVERAGE_GAP_OVERRIDE on the deploy-day boundary).

ALTER TABLE morning_position_alerts ADD COLUMN IF NOT EXISTS coverage_responding SMALLINT;
ALTER TABLE morning_position_alerts ADD COLUMN IF NOT EXISTS coverage_total SMALLINT;

COMMENT ON COLUMN morning_position_alerts.coverage_responding IS
    'Number of positions analysts that returned views for the run that '
    'wrote this alert. NULL for legacy rows (skip COVERAGE_GAP_OVERRIDE).';
COMMENT ON COLUMN morning_position_alerts.coverage_total IS
    'Total analysts in the ensemble at the time of this run (currently 3). '
    'Stored to generalize when ensemble size changes. NULL for legacy rows.';
