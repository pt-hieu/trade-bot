-- Migration 157: Purge bad retrospective data for 2026-03-02
-- Retro had bugs: day_change used open→close (hiding gap-downs),
-- TRIM/EXIT counted as wins on unrealized P/L. Fixed in commit ffa9a71.

-- Child tables first (FK on record_id)
DELETE FROM daily_evaluations WHERE record_id IN (SELECT id FROM daily_records WHERE record_date = '2026-03-02');
DELETE FROM daily_recommendations WHERE record_id IN (SELECT id FROM daily_records WHERE record_date = '2026-03-02');
DELETE FROM midday_data WHERE record_id IN (SELECT id FROM daily_records WHERE record_date = '2026-03-02');
DELETE FROM midday_summaries WHERE record_id IN (SELECT id FROM daily_records WHERE record_date = '2026-03-02');
DELETE FROM mode_violations WHERE record_id IN (SELECT id FROM daily_records WHERE record_date = '2026-03-02');

-- Parent table
DELETE FROM daily_records WHERE record_date = '2026-03-02';

-- Date-keyed tables
DELETE FROM alert_effectiveness WHERE scan_date = '2026-03-02';
DELETE FROM calibration_insights WHERE scan_date = '2026-03-02';
