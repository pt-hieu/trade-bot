-- Migration 079: Performance analytics views
-- v_trade_r_multiples: R-multiple analysis for closed trades
-- v_strategy_regime_performance: Win rate by strategy × market regime
-- mv_relative_strength: 20-day RS vs VN-Index (materialized, refreshed daily in retro)

CREATE OR REPLACE VIEW v_trade_r_multiples AS
SELECT
    t.*,
    CASE
        WHEN t.exit_date IS NOT NULL AND t.entry_date IS NOT NULL
        THEN (t.exit_date - t.entry_date)
        ELSE NULL
    END AS hold_days
FROM trades_calculated t
WHERE t.status = 'CLOSED';

COMMENT ON VIEW v_trade_r_multiples IS 'Closed trades with R-multiple and hold duration';


CREATE OR REPLACE VIEW v_strategy_regime_performance AS
SELECT
    t.strategy,
    d.market_regime,
    COUNT(*) AS trades,
    ROUND(AVG(t.pl_pct)::NUMERIC, 2) AS avg_return_pct,
    ROUND(
        SUM(CASE WHEN t.pl_pct > 0 THEN 1 ELSE 0 END)::NUMERIC
        / NULLIF(COUNT(*), 0) * 100,
        1
    ) AS win_rate,
    ROUND(AVG(CASE WHEN t.pl_pct > 0 THEN t.pl_pct END)::NUMERIC, 2) AS avg_win_pct,
    ROUND(AVG(CASE WHEN t.pl_pct < 0 THEN t.pl_pct END)::NUMERIC, 2) AS avg_loss_pct
FROM trades_calculated t
LEFT JOIN daily_records d ON t.entry_date = d.record_date
WHERE t.status = 'CLOSED'
GROUP BY t.strategy, d.market_regime;

COMMENT ON VIEW v_strategy_regime_performance IS 'Win rate by strategy x market regime';


-- Materialized view: 20-day relative strength vs VN-Index
-- Refreshed daily in retrospective.py: REFRESH MATERIALIZED VIEW CONCURRENTLY mv_relative_strength
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_relative_strength AS
SELECT
    p.price_date AS scan_date,
    p.ticker,
    p.close_vnd,
    idx.close_vnd AS vnindex_close,
    CASE
        WHEN LAG(idx.close_vnd, 20) OVER (PARTITION BY p.ticker ORDER BY p.price_date) > 0
         AND LAG(p.close_vnd,   20) OVER (PARTITION BY p.ticker ORDER BY p.price_date) > 0
        THEN
            (p.close_vnd::FLOAT / LAG(p.close_vnd, 20) OVER (PARTITION BY p.ticker ORDER BY p.price_date))
          / (idx.close_vnd::FLOAT / LAG(idx.close_vnd, 20) OVER (PARTITION BY p.ticker ORDER BY p.price_date))
        ELSE NULL
    END AS rs_20d
FROM daily_prices p
JOIN daily_prices idx
    ON idx.price_date = p.price_date
    AND idx.ticker = 'VNINDEX'
WHERE p.ticker != 'VNINDEX';

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_rs_date_ticker
    ON mv_relative_strength(scan_date, ticker);

COMMENT ON MATERIALIZED VIEW mv_relative_strength IS '20-day RS vs VN-Index per ticker. Refresh: REFRESH MATERIALIZED VIEW CONCURRENTLY mv_relative_strength';
