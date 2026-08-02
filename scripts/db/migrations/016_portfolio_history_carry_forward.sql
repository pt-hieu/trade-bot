-- Fix portfolio value history to carry forward last known price
-- When a ticker is missing from daily_prices on a given date (e.g. weekend scan gap),
-- use the most recent prior price instead of dropping the holding entirely.
-- Requires dbowner connection (CREATE OR REPLACE VIEW is DDL)

CREATE OR REPLACE VIEW v_portfolio_value_history AS
WITH scan_dates AS (
  SELECT DISTINCT scan_date
  FROM daily_prices
  WHERE scan_date >= (SELECT MIN(entry_date) FROM trades_calculated)
),
active_trades AS (
  SELECT
    sd.scan_date,
    t.ticker,
    t.shares
  FROM scan_dates sd
  JOIN trades_calculated t
    ON t.entry_date <= sd.scan_date
    AND (t.exit_date IS NULL OR t.exit_date > sd.scan_date)
),
priced AS (
  SELECT
    at.scan_date,
    at.ticker,
    at.shares,
    (
      SELECT dp.close_vnd
      FROM daily_prices dp
      WHERE dp.ticker = at.ticker
        AND dp.scan_date <= at.scan_date
      ORDER BY dp.scan_date DESC
      LIMIT 1
    ) AS close_vnd
  FROM active_trades at
)
SELECT
  scan_date AS snapshot_date,
  SUM(shares * close_vnd)::BIGINT AS invested_value_vnd
FROM priced
WHERE close_vnd IS NOT NULL
GROUP BY scan_date
ORDER BY scan_date;
