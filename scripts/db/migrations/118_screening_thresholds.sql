-- Migration 118: Add quantitative screening thresholds to trading_config
--
-- These thresholds power the deterministic fundamental pre-filter that runs
-- after sector agents emit BUY signals, before extract_top_picks().
-- All values are in human-readable units (percentages, ratios).

ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS screen_max_pe FLOAT DEFAULT 20.0;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS screen_max_pb FLOAT DEFAULT 2.5;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS screen_min_roe_pct FLOAT DEFAULT 10.0;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS screen_min_margin_pct FLOAT DEFAULT 5.0;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS screen_max_de FLOAT DEFAULT 1.5;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS screen_bank_max_de FLOAT DEFAULT 12.0;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS screen_missing_data_policy VARCHAR(20) DEFAULT 'pass';
