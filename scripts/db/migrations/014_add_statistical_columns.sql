-- Migration 014: Add statistical analysis columns for probability assessments
-- Date: 2026-02-02
-- Description: Adds columns for closed_at_low, volume_vs_avg, and next_day_change tracking

-- closed_at_low: True if close price is in bottom 10% of day's range
-- Used to detect distribution days and potential reversal setups
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS closed_at_low BOOLEAN;

-- volume_vs_avg: Ratio of today's volume to 20-day average volume
-- Values > 1.5 indicate high volume (breakout confirmation, capitulation)
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS volume_vs_avg DECIMAL(8, 2);

-- next_day_change_pct: VN-Index change on the NEXT trading day
-- Populated during T+1 retrospective to enable outcome-based pattern analysis
ALTER TABLE daily_records ADD COLUMN IF NOT EXISTS next_day_change_pct DECIMAL(8, 4);

-- Indexes for statistical queries
CREATE INDEX IF NOT EXISTS idx_tech_closed_at_low ON daily_technicals(closed_at_low);
CREATE INDEX IF NOT EXISTS idx_tech_volume_vs_avg ON daily_technicals(volume_vs_avg);
CREATE INDEX IF NOT EXISTS idx_records_next_day_change ON daily_records(next_day_change_pct);

-- Composite index for common query pattern: RSI + closed_at_low
CREATE INDEX IF NOT EXISTS idx_tech_rsi_closed_low ON daily_technicals(rsi, closed_at_low);
