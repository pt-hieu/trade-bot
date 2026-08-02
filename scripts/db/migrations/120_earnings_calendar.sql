-- Migration 120: Earnings calendar for VN quarterly filing awareness
CREATE TABLE IF NOT EXISTS earnings_calendar (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    fiscal_quarter VARCHAR(10) NOT NULL,
    expected_date DATE,
    actual_date DATE,
    status VARCHAR(20) DEFAULT 'upcoming',
    pre_price_vnd BIGINT,
    pre_rsi FLOAT,
    pre_pe FLOAT,
    post_price_vnd BIGINT,
    surprise_direction VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, fiscal_quarter)
);
CREATE INDEX IF NOT EXISTS idx_earnings_calendar_upcoming ON earnings_calendar (expected_date) WHERE status = 'upcoming';
CREATE INDEX IF NOT EXISTS idx_earnings_calendar_ticker ON earnings_calendar (ticker, expected_date);
