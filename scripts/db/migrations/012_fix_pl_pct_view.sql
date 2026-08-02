-- Fix v_recent_trades: pl_pct is already stored as percentage, don't multiply by 100
DROP VIEW IF EXISTS v_recent_trades CASCADE;
CREATE VIEW v_recent_trades AS
SELECT
    t.id,
    t.ticker,
    t.plan_type,
    t.strategy,
    t.entry_date,
    t.entry_price_vnd,
    t.exit_date,
    t.exit_price_vnd,
    t.shares,
    t.buy_total_vnd,
    t.pl_gross_vnd,
    t.pl_net_vnd,
    ROUND(t.pl_pct, 2) AS pl_pct,
    t.exit_date - t.entry_date AS days_held,
    CASE WHEN t.status != 'CLOSED' THEN NULL WHEN t.pl_net_vnd >= 0 THEN 'WIN' ELSE 'LOSS' END AS result,
    t.status
FROM trades_calculated t
ORDER BY COALESCE(t.exit_date, t.entry_date) DESC
LIMIT 20;
