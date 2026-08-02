-- Migration 076: Insider transaction tracking
-- Stores insider buy/sell registrations from vnstock VCI source.
-- Refreshed weekly via enrich_events.py.

CREATE TABLE IF NOT EXISTS insider_transactions (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    trader_name TEXT,
    trader_position TEXT,
    action VARCHAR(10),         -- BUY or SELL
    shares_registered INTEGER,
    shares_executed INTEGER,
    start_date DATE,
    end_date DATE,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, trader_name, start_date, action)
);

CREATE INDEX IF NOT EXISTS idx_insider_ticker ON insider_transactions(ticker);
CREATE INDEX IF NOT EXISTS idx_insider_start_date ON insider_transactions(start_date DESC);
CREATE INDEX IF NOT EXISTS idx_insider_ticker_date ON insider_transactions(ticker, start_date DESC);

COMMENT ON TABLE insider_transactions IS 'Insider buy/sell registrations from VCI, refreshed weekly';
