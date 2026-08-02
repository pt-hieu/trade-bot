-- Daily returns view for risk metric calculations (Beta, Sharpe, Sortino)
-- Computes daily % returns from daily_prices using LAG window function
-- Works for all tickers including VNINDEX benchmark

CREATE VIEW v_daily_returns AS
WITH ordered AS (
  SELECT
    ticker,
    scan_date,
    close_vnd,
    LAG(close_vnd) OVER (PARTITION BY ticker ORDER BY scan_date) AS prev_close
  FROM daily_prices
  WHERE close_vnd > 0
)
SELECT
  ticker,
  scan_date,
  close_vnd,
  prev_close,
  (close_vnd - prev_close)::NUMERIC / prev_close AS daily_return
FROM ordered
WHERE prev_close IS NOT NULL AND prev_close > 0;
