-- Migration 340: Calibration staleness observability (SWI-15).
--
-- Adds two columns so the LLM-facing staleness banner can be driven from
-- the calibration_insights row itself instead of a multi-table join.
--
-- last_trade_exit_date: most recent closed-trade exit date contributing
--   to avg_actual_rr. Enables "N days since last trade exit" banner.
-- swing_sample_size: swing-section sample count from learnings_summary,
--   persisted here so the banner reads from one row.

ALTER TABLE calibration_insights ADD COLUMN IF NOT EXISTS last_trade_exit_date DATE;
ALTER TABLE calibration_insights ADD COLUMN IF NOT EXISTS swing_sample_size INTEGER;

COMMENT ON COLUMN calibration_insights.last_trade_exit_date IS
    'Most recent closed-trade exit date contributing to avg_actual_rr. '
    'NULL = legacy row or no closed trades in window.';
COMMENT ON COLUMN calibration_insights.swing_sample_size IS
    'Swing-section sample count from learnings_summary, persisted to '
    'enable single-row staleness banner reads.';
