-- Add sentiment scoring columns to articles table
-- Sentiment extracted during article processing pipeline

ALTER TABLE articles ADD COLUMN IF NOT EXISTS
    sentiment_score FLOAT;  -- -1.0 (bearish) to +1.0 (bullish), NULL = unscored

ALTER TABLE articles ADD COLUMN IF NOT EXISTS
    sentiment_tickers TEXT[];  -- tickers mentioned in article

COMMENT ON COLUMN articles.sentiment_score IS
    'Per-article sentiment: -1.0 bearish to +1.0 bullish. Extracted by LLM during scoring.';

-- Index for aggregation queries (per-ticker per-date sentiment)
CREATE INDEX IF NOT EXISTS idx_articles_sentiment
    ON articles(sentiment_score) WHERE sentiment_score IS NOT NULL;
