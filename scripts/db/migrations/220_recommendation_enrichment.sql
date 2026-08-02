-- Migration 220: recommendation_enrichment
-- Type: DDL (requires owner connection)
--
-- Adds structured data columns to daily_recommendations that were previously
-- lost in the text round-trip (Phase 3b picks → synthesis prose → LLM parser).
-- Preserves all 29 fields from extract_top_picks() directly in DB.
--
-- Usage: uv run python scripts/db/run_migration.py 220_recommendation_enrichment.sql

-- Picks-sourced fields (from compute_trade_setup_async / strategy_classifier / Monte Carlo)
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS risk_reward DOUBLE PRECISION;
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS conservative_target_vnd BIGINT;
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS conservative_rr DOUBLE PRECISION;
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS aggressive_target_vnd BIGINT;
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS aggressive_rr DOUBLE PRECISION;
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS verdict VARCHAR(20);
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS volume_vs_avg DOUBLE PRECISION;
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS volume_confirmed BOOLEAN;
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS pattern_name VARCHAR(50);

-- Monte Carlo simulation results
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS sim_ev DOUBLE PRECISION;
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS sim_p_target DOUBLE PRECISION;
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS sim_p_stop DOUBLE PRECISION;

-- Belief aggregation
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS belief_conviction DOUBLE PRECISION;

-- Provenance and context
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS source VARCHAR(30);
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS urgency VARCHAR(20);
ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS counter_thesis TEXT;

-- Index on source for filtering by provenance
CREATE INDEX IF NOT EXISTS idx_daily_recs_source ON daily_recommendations(source) WHERE source IS NOT NULL;
