-- Migration 124: Thesis tracker tables for longterm watchlist

CREATE TABLE IF NOT EXISTS thesis_tracker (
    ticker VARCHAR(10) PRIMARY KEY,
    pillars JSONB DEFAULT '[]',
    kill_criteria JSONB DEFAULT '[]',
    conviction_history JSONB DEFAULT '[]',
    overall_thesis_status VARCHAR(20) DEFAULT 'INTACT',
    broken_count INT DEFAULT 0,
    weakening_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS thesis_updates (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) REFERENCES thesis_tracker(ticker) ON DELETE CASCADE,
    update_date DATE DEFAULT CURRENT_DATE,
    source VARCHAR(50),
    pillar_changes JSONB,
    kill_criteria_changes JSONB,
    conviction_change JSONB,
    data_point TEXT,
    impact TEXT,
    action_taken TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_thesis_updates_ticker
ON thesis_updates (ticker, update_date DESC);

CREATE INDEX IF NOT EXISTS idx_thesis_tracker_status
ON thesis_tracker (overall_thesis_status)
WHERE overall_thesis_status != 'INTACT';
