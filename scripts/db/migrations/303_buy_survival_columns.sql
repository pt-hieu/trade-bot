-- Track BUY signal funnel for survival rate monitoring.
-- Detects compounding gate regressions (conservatism death spiral).
ALTER TABLE daily_records ADD COLUMN IF NOT EXISTS buy_signal_count INTEGER;
ALTER TABLE daily_records ADD COLUMN IF NOT EXISTS buy_rec_count INTEGER;
