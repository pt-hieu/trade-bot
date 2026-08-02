-- Financial statements and ratios tables for fundamental analysis.
-- Deduplication via UNIQUE constraints. Use ON CONFLICT DO UPDATE for refresh.

CREATE TABLE IF NOT EXISTS financial_statements (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    statement_type VARCHAR(20) NOT NULL,  -- income, balance_sheet, cash_flow
    report_period VARCHAR(10) NOT NULL,   -- 2025-Q3, 2024
    period_type VARCHAR(10) NOT NULL,     -- quarter, year
    data JSONB NOT NULL,                  -- full statement row as JSON
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, statement_type, report_period)
);

CREATE INDEX IF NOT EXISTS idx_fin_stmt_ticker ON financial_statements(ticker);
CREATE INDEX IF NOT EXISTS idx_fin_stmt_period ON financial_statements(report_period);

CREATE TABLE IF NOT EXISTS financial_ratios (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    report_period VARCHAR(10) NOT NULL,       -- 2025-Q3, 2024
    period_type VARCHAR(10) NOT NULL,         -- quarter, year
    -- Profitability
    return_on_equity NUMERIC,
    return_on_assets NUMERIC,
    net_profit_margin NUMERIC,
    gross_profit_margin NUMERIC,
    operating_profit_margin NUMERIC,
    earnings_per_share NUMERIC,
    -- Valuation
    price_to_earnings NUMERIC,
    price_to_book NUMERIC,
    -- Leverage & Liquidity
    debt_to_equity NUMERIC,
    current_ratio NUMERIC,
    -- Overflow for less common ratios
    extra JSONB,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, report_period)
);

CREATE INDEX IF NOT EXISTS idx_fin_ratio_ticker ON financial_ratios(ticker);
