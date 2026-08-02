-- Migration 219: advocate_reviews audit trail table
-- Type: DDL (requires owner connection)
--
-- Usage: uv run python scripts/db/run_migration.py 219_advocate_reviews_table.sql

CREATE TABLE IF NOT EXISTS advocate_reviews (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    record_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    reviewer_type VARCHAR(10) NOT NULL,
    verdict VARCHAR(10) NOT NULL,
    confidence DECIMAL(4,3) NOT NULL,
    key_arguments JSONB NOT NULL DEFAULT '[]',
    blind_spots JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_advocate_reviews_date ON advocate_reviews(record_date);
CREATE INDEX IF NOT EXISTS idx_advocate_reviews_ticker ON advocate_reviews(ticker, record_date DESC);
