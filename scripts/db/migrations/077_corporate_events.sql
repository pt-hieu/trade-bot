-- Migration 077: Corporate events (dividends, AGMs, splits)
-- Stores upcoming and recent events per ticker.
-- Refreshed weekly via enrich_events.py.

CREATE TABLE IF NOT EXISTS corporate_events (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    event_type VARCHAR(50),     -- cash_dividend, stock_dividend, agm, split, bonus, rights
    event_title TEXT,
    ex_date DATE,
    record_date DATE,
    value DECIMAL(16,4),        -- cash per share or ratio (e.g., 0.20 = 20% bonus)
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, event_type, ex_date)
);

CREATE INDEX IF NOT EXISTS idx_corp_events_ticker ON corporate_events(ticker);
CREATE INDEX IF NOT EXISTS idx_corp_events_ex_date ON corporate_events(ex_date DESC);
CREATE INDEX IF NOT EXISTS idx_corp_events_upcoming ON corporate_events(ex_date);

COMMENT ON TABLE corporate_events IS 'Corporate events (dividends, AGMs, splits) from VCI, refreshed weekly';
COMMENT ON COLUMN corporate_events.value IS 'Cash per share (VND) or ratio for stock events';
