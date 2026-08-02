-- =====================================================
-- MIGRATION 010: Split Views by Plan Type (SWING vs LONGTERM)
-- =====================================================
-- Updates swing views to filter by plan_type = 'SWING'
-- Creates new long-term views for 4-year investment tracking
-- =====================================================

-- =====================================================
-- SWING TRADING VIEWS (Updated with plan_type filter)
-- =====================================================

-- 1. v_swing_metrics - Summary Dashboard (SWING only)
DROP VIEW IF EXISTS v_swing_metrics CASCADE;
CREATE VIEW v_swing_metrics AS
WITH closed_trades AS (
    SELECT
        pl_net_vnd,
        pl_gross_vnd,
        entry_date,
        exit_date
    FROM trades_calculated
    WHERE status = 'CLOSED' AND plan_type = 'SWING'
),
stats AS (
    SELECT
        COUNT(*) AS total_trades,
        SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN pl_net_vnd < 0 THEN 1 ELSE 0 END) AS losses,
        SUM(pl_net_vnd) AS total_return,
        AVG(CASE WHEN pl_net_vnd > 0 THEN pl_net_vnd END) AS avg_win,
        AVG(CASE WHEN pl_net_vnd < 0 THEN pl_net_vnd END) AS avg_loss,
        SUM(CASE WHEN pl_net_vnd > 0 THEN pl_net_vnd ELSE 0 END) AS gross_profit,
        ABS(SUM(CASE WHEN pl_net_vnd < 0 THEN pl_net_vnd ELSE 0 END)) AS gross_loss,
        AVG(exit_date - entry_date) AS avg_holding_days
    FROM closed_trades
)
SELECT
    total_trades,
    wins,
    losses,
    ROUND(wins::NUMERIC / NULLIF(total_trades, 0) * 100, 1) AS win_rate,
    total_return AS total_return_vnd,
    avg_win::BIGINT AS avg_win_vnd,
    avg_loss::BIGINT AS avg_loss_vnd,
    ROUND(gross_profit::NUMERIC / NULLIF(gross_loss, 0), 2) AS profit_factor,
    ROUND(total_return::NUMERIC / NULLIF(total_trades, 0))::BIGINT AS expectancy_vnd,
    ROUND(avg_holding_days::NUMERIC, 1) AS avg_holding_days
FROM stats;


-- 2. v_metrics_by_strategy - Strategy Breakdown (SWING only)
DROP VIEW IF EXISTS v_metrics_by_strategy CASCADE;
CREATE VIEW v_metrics_by_strategy AS
SELECT
    strategy,
    COUNT(*) AS trades,
    SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN pl_net_vnd < 0 THEN 1 ELSE 0 END) AS losses,
    ROUND(SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) AS win_rate,
    AVG(CASE WHEN pl_net_vnd > 0 THEN pl_net_vnd END)::BIGINT AS avg_win_vnd,
    AVG(CASE WHEN pl_net_vnd < 0 THEN pl_net_vnd END)::BIGINT AS avg_loss_vnd,
    SUM(pl_net_vnd) AS total_pl_vnd,
    ROUND(
        SUM(CASE WHEN pl_net_vnd > 0 THEN pl_net_vnd ELSE 0 END)::NUMERIC /
        NULLIF(ABS(SUM(CASE WHEN pl_net_vnd < 0 THEN pl_net_vnd ELSE 0 END)), 0),
        2
    ) AS profit_factor,
    ROUND(SUM(pl_net_vnd)::NUMERIC / NULLIF(COUNT(*), 0))::BIGINT AS expectancy_vnd,
    ROUND(AVG(exit_date - entry_date)::NUMERIC, 1) AS avg_holding_days
FROM trades_calculated
WHERE status = 'CLOSED' AND plan_type = 'SWING'
GROUP BY strategy
ORDER BY total_pl_vnd DESC;


-- 3. v_metrics_by_ticker - Per-Stock Performance (SWING only)
DROP VIEW IF EXISTS v_metrics_by_ticker CASCADE;
CREATE VIEW v_metrics_by_ticker AS
SELECT
    ticker,
    COUNT(*) AS trades,
    SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN pl_net_vnd < 0 THEN 1 ELSE 0 END) AS losses,
    ROUND(SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) AS win_rate,
    SUM(pl_net_vnd) AS total_pl_vnd,
    ROUND(AVG(pl_pct) * 100, 2) AS avg_pl_pct,
    MAX(pl_net_vnd) AS best_trade_vnd,
    MIN(pl_net_vnd) AS worst_trade_vnd,
    MAX(entry_date) AS last_trade_date
FROM trades_calculated
WHERE status = 'CLOSED' AND plan_type = 'SWING'
GROUP BY ticker
ORDER BY total_pl_vnd DESC;


-- 4. v_metrics_monthly - Time Series (SWING only)
DROP VIEW IF EXISTS v_metrics_monthly CASCADE;
CREATE VIEW v_metrics_monthly AS
WITH monthly AS (
    SELECT
        TO_CHAR(exit_date, 'YYYY-MM') AS month,
        COUNT(*) AS trades,
        SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END) AS wins,
        SUM(pl_net_vnd) AS net_pl_vnd
    FROM trades_calculated
    WHERE status = 'CLOSED' AND exit_date IS NOT NULL AND plan_type = 'SWING'
    GROUP BY TO_CHAR(exit_date, 'YYYY-MM')
)
SELECT
    month,
    trades,
    wins,
    trades - wins AS losses,
    ROUND(wins::NUMERIC / NULLIF(trades, 0) * 100, 1) AS win_rate,
    net_pl_vnd,
    SUM(net_pl_vnd) OVER (ORDER BY month) AS cumulative_pl_vnd
FROM monthly
ORDER BY month DESC;


-- 5. v_rolling_performance - Rolling Windows (SWING only)
DROP VIEW IF EXISTS v_rolling_performance CASCADE;
CREATE VIEW v_rolling_performance AS
WITH periods AS (
    SELECT '7d' AS period, 7 AS days
    UNION ALL SELECT '30d', 30
    UNION ALL SELECT '90d', 90
),
rolling AS (
    SELECT
        p.period,
        p.days,
        COUNT(t.*) AS trades,
        SUM(CASE WHEN t.pl_net_vnd > 0 THEN 1 ELSE 0 END) AS wins,
        SUM(t.pl_net_vnd) AS net_pl
    FROM periods p
    LEFT JOIN trades_calculated t ON
        t.status = 'CLOSED'
        AND t.plan_type = 'SWING'
        AND t.exit_date >= CURRENT_DATE - p.days
    GROUP BY p.period, p.days
)
SELECT
    period,
    trades,
    wins,
    trades - wins AS losses,
    ROUND(wins::NUMERIC / NULLIF(trades, 0) * 100, 1) AS win_rate,
    net_pl AS net_pl_vnd,
    ROUND(net_pl::NUMERIC / NULLIF(trades, 0))::BIGINT AS expectancy_vnd
FROM rolling
ORDER BY days;


-- 6. v_swing_positions - Open Swing Positions
DROP VIEW IF EXISTS v_swing_positions CASCADE;
CREATE VIEW v_swing_positions AS
SELECT
    p.ticker,
    p.shares,
    p.avg_cost_vnd,
    p.current_price_vnd,
    p.cost_basis_vnd,
    p.market_value_vnd,
    p.market_value_vnd - p.cost_basis_vnd AS unrealized_pl_vnd,
    CASE
        WHEN p.cost_basis_vnd > 0
        THEN ROUND((p.market_value_vnd - p.cost_basis_vnd)::NUMERIC / p.cost_basis_vnd * 100, 2)
        ELSE 0
    END AS unrealized_pl_pct,
    t.entry_date,
    CURRENT_DATE - t.entry_date AS days_held,
    t.strategy
FROM portfolio_holdings p
LEFT JOIN LATERAL (
    SELECT entry_date, strategy
    FROM trades_calculated
    WHERE ticker = p.ticker AND status = 'OPEN' AND plan_type = 'SWING'
    ORDER BY entry_date DESC
    LIMIT 1
) t ON true
WHERE p.holding_type != 'Cash' AND p.shares > 0 AND p.plan_type = 'SWING'
ORDER BY p.market_value_vnd DESC;


-- =====================================================
-- LONG-TERM INVESTMENT VIEWS (New)
-- =====================================================

-- 7. v_longterm_metrics - Long-term Portfolio Summary
DROP VIEW IF EXISTS v_longterm_metrics CASCADE;
CREATE VIEW v_longterm_metrics AS
WITH holdings AS (
    SELECT
        SUM(cost_basis_vnd) AS total_cost_basis,
        SUM(market_value_vnd) AS total_market_value,
        COUNT(*) AS position_count
    FROM portfolio_holdings
    WHERE holding_type != 'Cash' AND plan_type = 'LONGTERM' AND shares > 0
),
realized AS (
    SELECT
        COUNT(*) AS closed_trades,
        SUM(pl_net_vnd) AS realized_pl
    FROM trades_calculated
    WHERE status = 'CLOSED' AND plan_type = 'LONGTERM'
)
SELECT
    h.position_count,
    h.total_cost_basis,
    h.total_market_value,
    h.total_market_value - h.total_cost_basis AS unrealized_pl_vnd,
    ROUND((h.total_market_value - h.total_cost_basis)::NUMERIC / NULLIF(h.total_cost_basis, 0) * 100, 2) AS unrealized_pl_pct,
    COALESCE(r.realized_pl, 0) AS realized_pl_vnd,
    (h.total_market_value - h.total_cost_basis) + COALESCE(r.realized_pl, 0) AS total_return_vnd
FROM holdings h, realized r;


-- 8. v_longterm_positions - Long-term Holdings Detail
DROP VIEW IF EXISTS v_longterm_positions CASCADE;
CREATE VIEW v_longterm_positions AS
SELECT
    p.ticker,
    p.shares,
    p.avg_cost_vnd,
    p.current_price_vnd,
    p.cost_basis_vnd,
    p.market_value_vnd,
    p.market_value_vnd - p.cost_basis_vnd AS unrealized_pl_vnd,
    CASE
        WHEN p.cost_basis_vnd > 0
        THEN ROUND((p.market_value_vnd - p.cost_basis_vnd)::NUMERIC / p.cost_basis_vnd * 100, 2)
        ELSE 0
    END AS unrealized_pl_pct,
    t.entry_date AS first_entry_date,
    CURRENT_DATE - t.entry_date AS days_held,
    s.display_name AS sector
FROM portfolio_holdings p
LEFT JOIN LATERAL (
    SELECT MIN(entry_date) AS entry_date
    FROM trades_calculated
    WHERE ticker = p.ticker AND plan_type = 'LONGTERM'
) t ON true
LEFT JOIN stocks st ON p.ticker = st.ticker
LEFT JOIN sectors s ON st.sector_id = s.id
WHERE p.holding_type != 'Cash' AND p.shares > 0 AND p.plan_type = 'LONGTERM'
ORDER BY p.market_value_vnd DESC;


-- 9. v_longterm_allocation - Sector Allocation vs Target
DROP VIEW IF EXISTS v_longterm_allocation CASCADE;
CREATE VIEW v_longterm_allocation AS
WITH holdings_by_sector AS (
    SELECT
        COALESCE(s.name, 'other') AS sector,
        COALESCE(s.display_name, 'Other') AS sector_display,
        SUM(p.market_value_vnd) AS market_value
    FROM portfolio_holdings p
    LEFT JOIN stocks st ON p.ticker = st.ticker
    LEFT JOIN sectors s ON st.sector_id = s.id
    WHERE p.holding_type != 'Cash' AND p.shares > 0 AND p.plan_type = 'LONGTERM'
    GROUP BY s.name, s.display_name
),
total AS (
    SELECT SUM(market_value) AS total_value FROM holdings_by_sector
),
targets AS (
    -- Target allocation: 50% tech, 35% real_estate, 15% banking
    SELECT 'technology' AS sector, 50.0 AS target_pct
    UNION ALL SELECT 'real_estate', 35.0
    UNION ALL SELECT 'banking', 15.0
)
SELECT
    h.sector_display AS sector,
    h.market_value AS market_value_vnd,
    ROUND(h.market_value::NUMERIC / NULLIF(t.total_value, 0) * 100, 1) AS actual_pct,
    COALESCE(tg.target_pct, 0) AS target_pct,
    ROUND(h.market_value::NUMERIC / NULLIF(t.total_value, 0) * 100 - COALESCE(tg.target_pct, 0), 1) AS drift_pct,
    CASE
        WHEN ROUND(h.market_value::NUMERIC / NULLIF(t.total_value, 0) * 100, 1) > COALESCE(tg.target_pct, 0) + 5 THEN 'OVERWEIGHT'
        WHEN ROUND(h.market_value::NUMERIC / NULLIF(t.total_value, 0) * 100, 1) < COALESCE(tg.target_pct, 0) - 5 THEN 'UNDERWEIGHT'
        ELSE 'ON_TARGET'
    END AS status
FROM holdings_by_sector h
CROSS JOIN total t
LEFT JOIN targets tg ON h.sector = tg.sector
ORDER BY h.market_value DESC;


-- 10. v_longterm_entry_zones - Distance from Entry Zones
DROP VIEW IF EXISTS v_longterm_entry_zones CASCADE;
CREATE VIEW v_longterm_entry_zones AS
SELECT
    lw.ticker,
    lw.entry_zone_vnd,
    p.current_price_vnd,
    CASE
        WHEN p.current_price_vnd <= lw.entry_zone_vnd THEN 'BUY_ZONE'
        WHEN p.current_price_vnd <= lw.entry_zone_vnd * 1.05 THEN 'NEAR_ENTRY'
        WHEN p.current_price_vnd <= lw.entry_zone_vnd * 1.15 THEN 'WATCH'
        ELSE 'WAIT'
    END AS zone_status,
    ROUND((p.current_price_vnd - lw.entry_zone_vnd)::NUMERIC / NULLIF(lw.entry_zone_vnd, 0) * 100, 1) AS distance_from_entry_pct,
    lw.conviction,
    p.shares AS currently_held,
    p.market_value_vnd AS position_value
FROM longterm_watchlist lw
LEFT JOIN portfolio_holdings p ON lw.ticker = p.ticker AND p.plan_type = 'LONGTERM'
ORDER BY
    CASE
        WHEN p.current_price_vnd <= lw.entry_zone_vnd THEN 1
        WHEN p.current_price_vnd <= lw.entry_zone_vnd * 1.05 THEN 2
        WHEN p.current_price_vnd <= lw.entry_zone_vnd * 1.15 THEN 3
        ELSE 4
    END,
    lw.conviction DESC;


-- 11. v_longterm_monthly - Monthly P/L Trend (LONGTERM)
DROP VIEW IF EXISTS v_longterm_monthly CASCADE;
CREATE VIEW v_longterm_monthly AS
WITH monthly AS (
    SELECT
        TO_CHAR(exit_date, 'YYYY-MM') AS month,
        COUNT(*) AS trades,
        SUM(pl_net_vnd) AS realized_pl_vnd
    FROM trades_calculated
    WHERE status = 'CLOSED' AND exit_date IS NOT NULL AND plan_type = 'LONGTERM'
    GROUP BY TO_CHAR(exit_date, 'YYYY-MM')
)
SELECT
    month,
    trades,
    realized_pl_vnd,
    SUM(realized_pl_vnd) OVER (ORDER BY month) AS cumulative_realized_vnd
FROM monthly
ORDER BY month DESC;


-- 12. v_longterm_alerts - Long-term Position Alerts
DROP VIEW IF EXISTS v_longterm_alerts CASCADE;
CREATE VIEW v_longterm_alerts AS
WITH position_data AS (
    SELECT
        p.ticker,
        p.market_value_vnd,
        p.cost_basis_vnd,
        CASE
            WHEN p.cost_basis_vnd > 0
            THEN (p.market_value_vnd - p.cost_basis_vnd)::NUMERIC / p.cost_basis_vnd * 100
            ELSE 0
        END AS pl_pct,
        lw.entry_zone_vnd,
        p.current_price_vnd
    FROM portfolio_holdings p
    LEFT JOIN longterm_watchlist lw ON p.ticker = lw.ticker
    WHERE p.holding_type != 'Cash' AND p.shares > 0 AND p.plan_type = 'LONGTERM'
),
total AS (
    SELECT SUM(market_value_vnd) AS total_value FROM position_data
)
SELECT * FROM (
    -- OVERWEIGHT: Position > 40% of portfolio (need to trim)
    SELECT
        p.ticker,
        'OVERWEIGHT' AS alert_type,
        ROUND(p.market_value_vnd::NUMERIC / NULLIF(t.total_value, 0) * 100, 1) AS current_value,
        'Position is ' || ROUND(p.market_value_vnd::NUMERIC / NULLIF(t.total_value, 0) * 100, 1) || '% of portfolio. Consider trimming.' AS message
    FROM position_data p, total t
    WHERE p.market_value_vnd::NUMERIC / NULLIF(t.total_value, 0) > 0.40

    UNION ALL

    -- BIG_GAINER: Up >50% (consider taking some profit)
    SELECT
        ticker,
        'BIG_GAINER',
        ROUND(pl_pct, 1),
        'Position up ' || ROUND(pl_pct, 1) || '%. Consider trimming to lock in gains.'
    FROM position_data
    WHERE pl_pct > 50

    UNION ALL

    -- BACK_IN_ZONE: Price returned to entry zone (opportunity to add)
    SELECT
        ticker,
        'BACK_IN_ZONE',
        current_price_vnd,
        'Price returned to entry zone (' || entry_zone_vnd || '). Consider adding.'
    FROM position_data
    WHERE entry_zone_vnd IS NOT NULL AND current_price_vnd <= entry_zone_vnd
) alerts
ORDER BY alert_type, ticker;


-- =====================================================
-- UPDATE EXISTING VIEWS to use plan_type
-- =====================================================

-- Update v_open_positions to only show SWING
DROP VIEW IF EXISTS v_open_positions CASCADE;
CREATE VIEW v_open_positions AS
SELECT * FROM v_swing_positions;

-- Update v_recent_trades to show both with plan_type column
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
    ROUND(t.pl_pct * 100, 2) AS pl_pct,
    t.exit_date - t.entry_date AS days_held,
    CASE WHEN t.pl_net_vnd > 0 THEN 'WIN' ELSE 'LOSS' END AS result,
    t.status
FROM trades_calculated t
ORDER BY COALESCE(t.exit_date, t.entry_date) DESC
LIMIT 20;


-- Update v_capital_efficiency to show SWING only
DROP VIEW IF EXISTS v_capital_efficiency CASCADE;
CREATE VIEW v_capital_efficiency AS
WITH holdings AS (
    SELECT
        SUM(CASE WHEN holding_type != 'Cash' THEN market_value_vnd ELSE 0 END) AS capital_deployed,
        SUM(CASE WHEN holding_type = 'Cash' THEN shares ELSE 0 END) AS capital_available,
        COUNT(CASE WHEN holding_type != 'Cash' THEN 1 END) AS position_count
    FROM portfolio_holdings
    WHERE plan_type = 'SWING' OR holding_type = 'Cash'
),
avg_size AS (
    SELECT AVG(buy_total_vnd) AS avg_position_size
    FROM trades_calculated
    WHERE status = 'CLOSED' AND plan_type = 'SWING'
)
SELECT
    h.capital_deployed,
    h.capital_available,
    ROUND(h.capital_deployed::NUMERIC / NULLIF(h.capital_deployed + h.capital_available, 0) * 100, 1) AS utilization_pct,
    ROUND(a.avg_position_size)::BIGINT AS avg_position_size_vnd,
    h.position_count
FROM holdings h, avg_size a;
