-- Portfolio value history view
-- Computes daily invested portfolio value from trades + daily prices
-- Combined SWING + LONGTERM values (no plan_type filter)
-- Requires dbowner connection (CREATE VIEW is DDL)

CREATE VIEW v_portfolio_value_history AS
WITH active_holdings AS (
  SELECT
    dp.scan_date,
    t.ticker,
    t.shares,
    dp.close_vnd
  FROM daily_prices dp
  JOIN trades_calculated t
    ON t.ticker = dp.ticker
    AND t.entry_date <= dp.scan_date
    AND (t.exit_date IS NULL OR t.exit_date > dp.scan_date)
  WHERE dp.scan_date >= (SELECT MIN(entry_date) FROM trades_calculated)
)
SELECT
  scan_date AS snapshot_date,
  SUM(shares * close_vnd)::BIGINT AS invested_value_vnd
FROM active_holdings
GROUP BY scan_date
ORDER BY scan_date;
