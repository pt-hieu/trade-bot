-- Migration: 004_add_composite_indexes.sql
-- Description: Add composite indexes for multi-column queries
-- Impact: HIGH - Optimizes get_ticker_technicals(ticker, scan_date) and article search

-- For get_ticker_technicals(ticker, scan_date) queries
-- Column order: ticker first (equality), scan_date second (range/DESC)
CREATE INDEX IF NOT EXISTS idx_daily_technicals_ticker_date
    ON daily_technicals(ticker, scan_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_levels_ticker_date
    ON daily_levels(ticker, scan_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_prices_ticker_date
    ON daily_prices(ticker, scan_date DESC);

-- For article search queries with date + query_name filter
CREATE INDEX IF NOT EXISTS idx_article_searches_date_query
    ON article_searches(scan_date, query_name);

-- For market regime history queries (ORDER BY scan_date DESC)
CREATE INDEX IF NOT EXISTS idx_market_regimes_scan_date_desc
    ON market_regimes(scan_date DESC);

-- For macro metrics history queries
CREATE INDEX IF NOT EXISTS idx_macro_metrics_scan_date_desc
    ON macro_metrics(scan_date DESC);
