-- Migration 090: Add USD/VND source and spread tracking to macro_metrics
-- Supports flip-flopping fix: standardize on SBV reference rate as primary source,
-- track spread between market rate and SBV rate as additional stress signal.

ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS usd_vnd_source VARCHAR(20);
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS usd_vnd_spread DECIMAL(10,2);
