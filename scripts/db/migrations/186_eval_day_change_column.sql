-- Add day_change column to daily_evaluations
-- pnl_percent stores cumulative position P/L (confusing for HOLDs)
-- day_change tracks single-day price movement, already computed in retro/compute.py
ALTER TABLE daily_evaluations ADD COLUMN IF NOT EXISTS day_change DECIMAL(8, 4);
