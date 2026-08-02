-- Track catalyst-related news article spikes for intraday detection.

CREATE TABLE IF NOT EXISTS catalyst_news_signals (
    id SERIAL PRIMARY KEY,
    catalyst_key VARCHAR(60) NOT NULL REFERENCES catalysts(catalyst_key),
    signal_date DATE NOT NULL,
    article_count INTEGER NOT NULL DEFAULT 0,
    is_spike BOOLEAN NOT NULL DEFAULT FALSE,
    sample_titles TEXT[],
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(catalyst_key, signal_date)
);

CREATE INDEX IF NOT EXISTS idx_catalyst_news_signals_date
ON catalyst_news_signals(signal_date DESC);
