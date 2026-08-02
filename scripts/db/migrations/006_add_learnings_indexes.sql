-- Migration: 006_add_learnings_indexes.sql
-- Description: Add indexes for learnings query optimizations
-- Impact: MEDIUM - Faster ORDER BY and JOIN operations

-- For ORDER BY recent_accuracy in get_ticker_insights()
CREATE INDEX IF NOT EXISTS idx_ticker_insights_accuracy
    ON ticker_insights(recent_accuracy DESC);

-- For filtered ORDER BY in get_winning_patterns()
CREATE INDEX IF NOT EXISTS idx_learning_patterns_type_win
    ON learning_patterns(pattern_type, win_rate DESC);

-- For JOIN in get_sector_insights()
CREATE INDEX IF NOT EXISTS idx_sector_insights_sector_id
    ON sector_insights(sector_id);

-- For daily_records date lookups
CREATE INDEX IF NOT EXISTS idx_daily_records_date_desc
    ON daily_records(record_date DESC);
