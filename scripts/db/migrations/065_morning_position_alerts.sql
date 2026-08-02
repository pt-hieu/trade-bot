-- Migration 065: Structured morning position alerts table
-- Stores position monitor output for structured midday handoff (no markdown parsing needed)

CREATE TABLE IF NOT EXISTS morning_position_alerts (
    id SERIAL PRIMARY KEY,
    scan_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    action VARCHAR(10) NOT NULL,
    urgency VARCHAR(10) NOT NULL,
    reason TEXT,
    target_price NUMERIC,
    stop_price NUMERIC,
    consensus VARCHAR(20),
    dissenting_views JSONB DEFAULT '[]',
    entry_price NUMERIC,
    pct_from_entry NUMERIC,
    weight_pct NUMERIC,
    volume_signal VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(scan_date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_morning_alerts_date ON morning_position_alerts(scan_date);
