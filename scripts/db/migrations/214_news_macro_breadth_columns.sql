-- Migration 214: Add published_at to articles, US indices + breadth to macro_metrics
-- Type: DDL (requires owner connection)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/214_news_macro_breadth_columns.sql

-- Article publish timestamps (from RSS pubDate)
ALTER TABLE articles ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ NULL;

-- US market indices (yfinance: ^GSPC, ^IXIC, ^DJI)
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS sp500_close NUMERIC NULL;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS sp500_change_pct NUMERIC NULL;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS nasdaq_close NUMERIC NULL;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS nasdaq_change_pct NUMERIC NULL;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS dow_close NUMERIC NULL;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS dow_change_pct NUMERIC NULL;

-- Market breadth (advance/decline from TopStock gainer/loser)
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS breadth_advance INT NULL;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS breadth_decline INT NULL;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS breadth_ratio NUMERIC NULL;
