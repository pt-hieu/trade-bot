-- Migration 075: Per-ticker daily flow data
-- Stores foreign investor, proprietary, and derived retail flow per stock per day.
-- Fetched after daily_scan via enrich_flow.py.

CREATE TABLE IF NOT EXISTS daily_flow (
    id SERIAL PRIMARY KEY,
    scan_date DATE NOT NULL,
    ticker VARCHAR(20) NOT NULL,
    -- Foreign investor flow (billion VND)
    foreign_buy_value DECIMAL(16,4),
    foreign_sell_value DECIMAL(16,4),
    foreign_net_value DECIMAL(16,4),
    foreign_room_remaining INTEGER,       -- shares remaining for foreign ownership
    foreign_ownership_pct DECIMAL(5,2),   -- current foreign ownership %
    -- Proprietary trading desk flow (billion VND)
    prop_buy_value DECIMAL(16,4),
    prop_sell_value DECIMAL(16,4),
    prop_net_value DECIMAL(16,4),
    -- Order statistics
    buy_orders INTEGER,
    sell_orders INTEGER,
    avg_buy_order_size DECIMAL(14,2),
    avg_sell_order_size DECIMAL(14,2),
    -- Derived: total - foreign - prop ≈ retail
    implied_retail_net DECIMAL(16,4),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(scan_date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_daily_flow_date ON daily_flow(scan_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_flow_ticker ON daily_flow(ticker);
CREATE INDEX IF NOT EXISTS idx_daily_flow_ticker_date ON daily_flow(ticker, scan_date DESC);

COMMENT ON TABLE daily_flow IS 'Per-ticker foreign/prop/retail flow enrichment from vnstock premium';
COMMENT ON COLUMN daily_flow.implied_retail_net IS 'Derived retail net = total market - foreign - prop';
