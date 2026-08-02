-- 092_backtest_results.sql
-- Store historical backtesting results per strategy.
-- Populated by scripts/backtest.py CLI tool.

CREATE TABLE IF NOT EXISTS backtest_results (
    id SERIAL PRIMARY KEY,
    strategy VARCHAR(20) NOT NULL,
    days_back INT NOT NULL,
    total_signals INT,
    win_rate_5d FLOAT,
    win_rate_10d FLOAT,
    win_rate_15d FLOAT,
    avg_return_5d FLOAT,
    avg_return_10d FLOAT,
    avg_return_15d FLOAT,
    expectancy_10d FLOAT,
    optimal_horizon INT,
    by_regime JSONB,
    computed_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(strategy, days_back)
);

CREATE INDEX IF NOT EXISTS idx_backtest_strategy ON backtest_results(strategy);
COMMENT ON TABLE backtest_results IS 'Per-strategy backtesting results from scripts/backtest.py';
