-- Migration 019: Add affected_tickers array to articles table
-- Enables ticker-based article lookup (e.g., find all articles mentioning FOX).

ALTER TABLE articles
ADD COLUMN IF NOT EXISTS affected_tickers TEXT[] DEFAULT '{}';

-- GIN index for efficient array containment queries
-- e.g., WHERE 'FOX' = ANY(affected_tickers)
CREATE INDEX IF NOT EXISTS idx_articles_tickers
ON articles USING GIN (affected_tickers);
