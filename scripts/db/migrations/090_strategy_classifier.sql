-- 090_strategy_classifier.sql
-- Add strategy classification columns to daily_recommendations.
-- Populated by picks.py strategy_classifier during morning brief generation.

ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS strategy VARCHAR(20);
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS strategy_confidence FLOAT;

COMMENT ON COLUMN daily_recommendations.strategy IS 'BOUNCE | TREND | BREAKOUT | DIVERGENCE | UNCLASSIFIED';
COMMENT ON COLUMN daily_recommendations.strategy_confidence IS '0.0-1.0 confidence in strategy classification';

CREATE INDEX IF NOT EXISTS idx_daily_recs_strategy ON daily_recommendations(strategy) WHERE strategy IS NOT NULL;
