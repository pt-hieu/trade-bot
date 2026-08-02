-- =====================================================
-- MIGRATION 008: Swing Trading Metrics Views
-- =====================================================
-- Creates 19 PostgreSQL views for comprehensive trading metrics
-- Designed to work with Neon Data API (PostgREST)
--
-- Categories:
--   Core Metrics (1-10)
--   Comparison Views (11-13)
--   Alert Views (14-15)
--   Advanced Views (16-19)
-- =====================================================

-- =====================================================
-- CORE METRICS VIEWS
-- =====================================================

-- 1. v_swing_metrics - Summary Dashboard (matches Notion metrics)
DROP VIEW IF EXISTS v_swing_metrics CASCADE;
CREATE VIEW v_swing_metrics AS
WITH closed_trades AS (
    SELECT
        pl_net_vnd,
        pl_gross_vnd,
        entry_date,
        exit_date
    FROM trades_calculated
    WHERE status = 'CLOSED'
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


-- 2. v_metrics_by_strategy - Strategy Breakdown
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
WHERE status = 'CLOSED'
GROUP BY strategy
ORDER BY total_pl_vnd DESC;


-- 3. v_metrics_by_ticker - Per-Stock Performance
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
WHERE status = 'CLOSED'
GROUP BY ticker
ORDER BY total_pl_vnd DESC;


-- 4. v_metrics_monthly - Time Series (Monthly)
DROP VIEW IF EXISTS v_metrics_monthly CASCADE;
CREATE VIEW v_metrics_monthly AS
WITH monthly AS (
    SELECT
        TO_CHAR(exit_date, 'YYYY-MM') AS month,
        COUNT(*) AS trades,
        SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END) AS wins,
        SUM(pl_net_vnd) AS net_pl_vnd
    FROM trades_calculated
    WHERE status = 'CLOSED' AND exit_date IS NOT NULL
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


-- 5. v_metrics_weekly - Time Series (Weekly)
DROP VIEW IF EXISTS v_metrics_weekly CASCADE;
CREATE VIEW v_metrics_weekly AS
WITH weekly AS (
    SELECT
        DATE_TRUNC('week', exit_date)::DATE AS week_start,
        COUNT(*) AS trades,
        SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END) AS wins,
        SUM(pl_net_vnd) AS net_pl_vnd
    FROM trades_calculated
    WHERE status = 'CLOSED' AND exit_date IS NOT NULL
    GROUP BY DATE_TRUNC('week', exit_date)
)
SELECT
    week_start,
    TO_CHAR(week_start, 'YYYY-WW') AS week_label,
    trades,
    wins,
    trades - wins AS losses,
    ROUND(wins::NUMERIC / NULLIF(trades, 0) * 100, 1) AS win_rate,
    net_pl_vnd,
    SUM(net_pl_vnd) OVER (ORDER BY week_start) AS cumulative_pl_vnd
FROM weekly
ORDER BY week_start DESC;


-- 6. v_streak_analysis - Win/Loss Streaks
DROP VIEW IF EXISTS v_streak_analysis CASCADE;
CREATE VIEW v_streak_analysis AS
WITH ordered_trades AS (
    SELECT
        exit_date,
        pl_net_vnd,
        CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END AS is_win,
        ROW_NUMBER() OVER (ORDER BY exit_date) AS rn
    FROM trades_calculated
    WHERE status = 'CLOSED' AND exit_date IS NOT NULL
),
streak_groups AS (
    SELECT
        *,
        rn - ROW_NUMBER() OVER (PARTITION BY is_win ORDER BY exit_date) AS streak_group
    FROM ordered_trades
),
streaks AS (
    SELECT
        is_win,
        streak_group,
        COUNT(*) AS streak_length,
        MIN(exit_date) AS streak_start,
        MAX(exit_date) AS streak_end
    FROM streak_groups
    GROUP BY is_win, streak_group
),
current_streak AS (
    SELECT
        CASE WHEN is_win = 1 THEN streak_length ELSE -streak_length END AS current_streak
    FROM streaks
    ORDER BY streak_end DESC
    LIMIT 1
)
SELECT
    COALESCE((SELECT current_streak FROM current_streak), 0) AS current_streak,
    COALESCE(MAX(CASE WHEN is_win = 1 THEN streak_length END), 0) AS max_win_streak,
    COALESCE(MAX(CASE WHEN is_win = 0 THEN streak_length END), 0) AS max_loss_streak,
    ROUND(AVG(streak_length)::NUMERIC, 1) AS avg_streak_length
FROM streaks;


-- 7. v_risk_metrics - Risk Management
DROP VIEW IF EXISTS v_risk_metrics CASCADE;
CREATE VIEW v_risk_metrics AS
WITH trade_series AS (
    SELECT
        exit_date,
        pl_net_vnd,
        SUM(pl_net_vnd) OVER (ORDER BY exit_date) AS cumulative_pl,
        buy_total_vnd
    FROM trades_calculated
    WHERE status = 'CLOSED' AND exit_date IS NOT NULL
    ORDER BY exit_date
),
peaks AS (
    SELECT
        exit_date,
        cumulative_pl,
        MAX(cumulative_pl) OVER (ORDER BY exit_date) AS running_peak
    FROM trade_series
),
drawdowns AS (
    SELECT
        cumulative_pl - running_peak AS drawdown_vnd
    FROM peaks
),
stats AS (
    SELECT
        MIN(drawdown_vnd) AS max_drawdown_vnd,
        AVG(buy_total_vnd) AS avg_position_size,
        STDDEV(pl_net_vnd) AS pl_stddev,
        AVG(pl_net_vnd) AS avg_pl
    FROM trade_series, drawdowns
)
SELECT
    max_drawdown_vnd,
    ROUND(max_drawdown_vnd::NUMERIC / NULLIF(10000000, 0) * 100, 2) AS max_drawdown_pct,  -- 10M capital
    ROUND(avg_pl::NUMERIC / NULLIF(pl_stddev, 0), 2) AS sharpe_proxy,
    ROUND(avg_position_size)::BIGINT AS avg_position_size_vnd,
    ROUND(
        (SELECT AVG(
            CASE
                WHEN pl_net_vnd > 0 AND pl_gross_vnd > 0
                THEN pl_gross_vnd::NUMERIC / NULLIF(buy_total_vnd - sell_total_vnd + pl_gross_vnd, 0)
                ELSE NULL
            END
        ) FROM trades_calculated WHERE status = 'CLOSED'),
        2
    ) AS avg_rr_achieved
FROM stats;


-- 8. v_holding_analysis - Timing Insights
DROP VIEW IF EXISTS v_holding_analysis CASCADE;
CREATE VIEW v_holding_analysis AS
SELECT
    ROUND(AVG(CASE WHEN pl_net_vnd > 0 THEN exit_date - entry_date END)::NUMERIC, 1) AS avg_hold_winners,
    ROUND(AVG(CASE WHEN pl_net_vnd < 0 THEN exit_date - entry_date END)::NUMERIC, 1) AS avg_hold_losers,
    SUM(CASE WHEN exit_date - entry_date < 7 THEN 1 ELSE 0 END) AS early_exits,
    SUM(CASE WHEN exit_date - entry_date > 30 THEN 1 ELSE 0 END) AS extended_holds,
    COUNT(*) AS total_closed_trades
FROM trades_calculated
WHERE status = 'CLOSED' AND exit_date IS NOT NULL;


-- 9. v_capital_efficiency - Capital Usage
DROP VIEW IF EXISTS v_capital_efficiency CASCADE;
CREATE VIEW v_capital_efficiency AS
WITH holdings AS (
    SELECT
        SUM(CASE WHEN holding_type != 'Cash' THEN market_value_vnd ELSE 0 END) AS capital_deployed,
        SUM(CASE WHEN holding_type = 'Cash' THEN shares ELSE 0 END) AS capital_available,  -- Cash stored in shares column as VND
        COUNT(CASE WHEN holding_type != 'Cash' THEN 1 END) AS position_count
    FROM portfolio_holdings
),
avg_size AS (
    SELECT AVG(buy_total_vnd) AS avg_position_size
    FROM trades_calculated
    WHERE status = 'CLOSED'
)
SELECT
    h.capital_deployed,
    h.capital_available,
    ROUND(h.capital_deployed::NUMERIC / NULLIF(h.capital_deployed + h.capital_available, 0) * 100, 1) AS utilization_pct,
    ROUND(a.avg_position_size)::BIGINT AS avg_position_size_vnd,
    h.position_count
FROM holdings h, avg_size a;


-- 10. v_goal_progress - Goal Tracking
DROP VIEW IF EXISTS v_goal_progress CASCADE;
CREATE VIEW v_goal_progress AS
SELECT
    id,
    name AS goal_name,
    target_vnd AS target,
    realized_vnd AS realized,
    ROUND(realized_vnd::NUMERIC / NULLIF(target_vnd, 0) * 100, 1) AS progress_pct,
    deadline,
    deadline - CURRENT_DATE AS days_remaining,
    CASE
        WHEN deadline > CURRENT_DATE AND (target_vnd - realized_vnd) > 0
        THEN ROUND((target_vnd - realized_vnd)::NUMERIC / NULLIF(deadline - CURRENT_DATE, 0))::BIGINT
        ELSE 0
    END AS required_daily_vnd,
    status,
    goal_type
FROM goals
WHERE status = 'Active'
ORDER BY deadline;


-- =====================================================
-- COMPARISON VIEWS
-- =====================================================

-- 11. v_metrics_mom - Month-over-Month Comparison
DROP VIEW IF EXISTS v_metrics_mom CASCADE;
CREATE VIEW v_metrics_mom AS
WITH monthly_stats AS (
    SELECT
        TO_CHAR(exit_date, 'YYYY-MM') AS month,
        COUNT(*) AS trades,
        SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0) * 100 AS win_rate,
        SUM(pl_net_vnd)::NUMERIC / NULLIF(COUNT(*), 0) AS expectancy,
        SUM(pl_net_vnd) AS net_pl
    FROM trades_calculated
    WHERE status = 'CLOSED' AND exit_date IS NOT NULL
    GROUP BY TO_CHAR(exit_date, 'YYYY-MM')
),
with_prev AS (
    SELECT
        month,
        trades,
        win_rate,
        expectancy,
        net_pl,
        LAG(win_rate) OVER (ORDER BY month) AS prev_win_rate,
        LAG(expectancy) OVER (ORDER BY month) AS prev_expectancy,
        LAG(net_pl) OVER (ORDER BY month) AS prev_net_pl
    FROM monthly_stats
)
SELECT
    month,
    trades,
    ROUND(win_rate, 1) AS win_rate,
    ROUND(prev_win_rate, 1) AS prev_win_rate,
    ROUND(win_rate - COALESCE(prev_win_rate, win_rate), 1) AS win_rate_change,
    CASE
        WHEN win_rate > COALESCE(prev_win_rate, win_rate) THEN 'UP'
        WHEN win_rate < COALESCE(prev_win_rate, win_rate) THEN 'DOWN'
        ELSE 'FLAT'
    END AS win_rate_trend,
    ROUND(expectancy)::BIGINT AS expectancy_vnd,
    ROUND(prev_expectancy)::BIGINT AS prev_expectancy_vnd,
    net_pl::BIGINT AS net_pl_vnd,
    prev_net_pl::BIGINT AS prev_net_pl_vnd
FROM with_prev
ORDER BY month DESC;


-- 12. v_metrics_wow - Week-over-Week Comparison
DROP VIEW IF EXISTS v_metrics_wow CASCADE;
CREATE VIEW v_metrics_wow AS
WITH weekly_stats AS (
    SELECT
        DATE_TRUNC('week', exit_date)::DATE AS week_start,
        COUNT(*) AS trades,
        SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0) * 100 AS win_rate,
        SUM(pl_net_vnd)::NUMERIC / NULLIF(COUNT(*), 0) AS expectancy,
        SUM(pl_net_vnd) AS net_pl
    FROM trades_calculated
    WHERE status = 'CLOSED' AND exit_date IS NOT NULL
    GROUP BY DATE_TRUNC('week', exit_date)
),
with_prev AS (
    SELECT
        week_start,
        trades,
        win_rate,
        expectancy,
        net_pl,
        LAG(win_rate) OVER (ORDER BY week_start) AS prev_win_rate,
        LAG(expectancy) OVER (ORDER BY week_start) AS prev_expectancy,
        LAG(net_pl) OVER (ORDER BY week_start) AS prev_net_pl
    FROM weekly_stats
)
SELECT
    week_start,
    TO_CHAR(week_start, 'YYYY-WW') AS week_label,
    trades,
    ROUND(win_rate, 1) AS win_rate,
    ROUND(prev_win_rate, 1) AS prev_win_rate,
    ROUND(win_rate - COALESCE(prev_win_rate, win_rate), 1) AS win_rate_change,
    CASE
        WHEN win_rate > COALESCE(prev_win_rate, win_rate) THEN 'UP'
        WHEN win_rate < COALESCE(prev_win_rate, win_rate) THEN 'DOWN'
        ELSE 'FLAT'
    END AS win_rate_trend,
    ROUND(expectancy)::BIGINT AS expectancy_vnd,
    net_pl::BIGINT AS net_pl_vnd
FROM with_prev
ORDER BY week_start DESC;


-- 13. v_rolling_performance - Rolling Windows (7d, 30d, 90d)
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
        COUNT(*) AS trades,
        SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END) AS wins,
        SUM(pl_net_vnd) AS net_pl
    FROM periods p
    LEFT JOIN trades_calculated t ON
        t.status = 'CLOSED'
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


-- =====================================================
-- ALERT VIEWS
-- =====================================================

-- 14. v_metric_alerts - Threshold Breaches
DROP VIEW IF EXISTS v_metric_alerts CASCADE;
CREATE VIEW v_metric_alerts AS
WITH metrics AS (
    SELECT * FROM v_swing_metrics
),
streak AS (
    SELECT * FROM v_streak_analysis
),
risk AS (
    SELECT * FROM v_risk_metrics
)
SELECT * FROM (
    -- Win Rate alerts
    SELECT
        CASE WHEN m.win_rate < 40 THEN 'CRITICAL' ELSE 'WARNING' END AS alert_type,
        'Win Rate' AS metric,
        m.win_rate AS current_value,
        '50-100%' AS threshold,
        'Win rate is ' || ROUND(m.win_rate, 1) || '%, below healthy range' AS message
    FROM metrics m
    WHERE m.win_rate < 50

    UNION ALL

    -- Profit Factor alerts
    SELECT
        CASE WHEN m.profit_factor < 1.0 THEN 'CRITICAL' ELSE 'WARNING' END,
        'Profit Factor',
        m.profit_factor,
        '>1.5',
        'Profit factor is ' || m.profit_factor || ', edge is weak'
    FROM metrics m
    WHERE m.profit_factor IS NOT NULL AND m.profit_factor < 1.5

    UNION ALL

    -- Expectancy alerts
    SELECT
        CASE WHEN m.expectancy_vnd < 0 THEN 'CRITICAL' ELSE 'WARNING' END,
        'Expectancy',
        m.expectancy_vnd,
        '>500K VND',
        'Expectancy is ' || COALESCE(m.expectancy_vnd::TEXT, '0') || ' VND'
    FROM metrics m
    WHERE m.expectancy_vnd IS NOT NULL AND m.expectancy_vnd < 500000

    UNION ALL

    -- Drawdown alerts
    SELECT
        CASE WHEN r.max_drawdown_pct < -20 THEN 'CRITICAL' ELSE 'WARNING' END,
        'Max Drawdown',
        r.max_drawdown_pct,
        '<10%',
        'Drawdown is ' || ABS(COALESCE(r.max_drawdown_pct, 0)) || '% of capital'
    FROM risk r
    WHERE r.max_drawdown_pct IS NOT NULL AND r.max_drawdown_pct < -10

    UNION ALL

    -- Holding period alerts
    SELECT
        CASE WHEN m.avg_holding_days > 60 THEN 'CRITICAL' ELSE 'WARNING' END,
        'Avg Holding Period',
        m.avg_holding_days,
        '<45 days',
        'Average hold is ' || COALESCE(m.avg_holding_days::TEXT, '0') || ' days, too long for swing'
    FROM metrics m
    WHERE m.avg_holding_days IS NOT NULL AND m.avg_holding_days > 45

    UNION ALL

    -- Loss streak alerts
    SELECT
        CASE WHEN s.current_streak <= -5 THEN 'CRITICAL' ELSE 'WARNING' END,
        'Loss Streak',
        ABS(s.current_streak),
        '<3',
        'Current loss streak: ' || ABS(s.current_streak) || ' trades'
    FROM streak s
    WHERE s.current_streak <= -3
) alerts
ORDER BY
    CASE alert_type WHEN 'CRITICAL' THEN 1 ELSE 2 END,
    metric;


-- 15. v_position_alerts - Position-Level Warnings
DROP VIEW IF EXISTS v_position_alerts CASCADE;
CREATE VIEW v_position_alerts AS
WITH position_data AS (
    SELECT
        p.ticker,
        p.shares,
        p.avg_cost_vnd,
        p.current_price_vnd,
        p.market_value_vnd,
        p.cost_basis_vnd,
        CASE
            WHEN p.cost_basis_vnd > 0
            THEN ROUND((p.market_value_vnd - p.cost_basis_vnd)::NUMERIC / p.cost_basis_vnd * 100, 2)
            ELSE 0
        END AS pl_pct,
        t.entry_date,
        CURRENT_DATE - t.entry_date AS days_held
    FROM portfolio_holdings p
    LEFT JOIN LATERAL (
        SELECT entry_date
        FROM trades_calculated
        WHERE ticker = p.ticker AND status = 'OPEN'
        ORDER BY entry_date DESC
        LIMIT 1
    ) t ON true
    WHERE p.holding_type != 'Cash' AND p.shares > 0
),
total_value AS (
    SELECT SUM(market_value_vnd) AS total FROM position_data
)
SELECT * FROM (
    -- STALE: Held > 30 days with < 5% gain
    SELECT
        ticker,
        'STALE' AS alert_type,
        days_held,
        pl_pct AS current_pl_pct,
        'Position held ' || days_held || ' days with only ' || pl_pct || '% gain. Consider exit.' AS message
    FROM position_data
    WHERE days_held > 30 AND pl_pct < 5

    UNION ALL

    -- UNDERWATER: > 10% loss
    SELECT
        ticker,
        'UNDERWATER',
        days_held,
        pl_pct,
        'Position down ' || ABS(pl_pct) || '%. Review stop-loss.' AS message
    FROM position_data
    WHERE pl_pct < -10

    UNION ALL

    -- OVERSIZED: Position > 30% of portfolio
    SELECT
        p.ticker,
        'OVERSIZED',
        p.days_held,
        p.pl_pct,
        'Position is ' || ROUND(p.market_value_vnd::NUMERIC / NULLIF(t.total, 0) * 100, 1) || '% of portfolio. Consider trimming.' AS message
    FROM position_data p, total_value t
    WHERE p.market_value_vnd::NUMERIC / NULLIF(t.total, 0) > 0.30
) alerts
ORDER BY
    CASE alert_type
        WHEN 'UNDERWATER' THEN 1
        WHEN 'OVERSIZED' THEN 2
        ELSE 3
    END,
    ticker;


-- =====================================================
-- ADVANCED VIEWS
-- =====================================================

-- 16. v_trade_quality - Trade Quality Score (simplified)
DROP VIEW IF EXISTS v_trade_quality CASCADE;
CREATE VIEW v_trade_quality AS
SELECT
    t.id,
    t.ticker,
    t.entry_date,
    t.exit_date,
    t.pl_pct,
    t.pl_net_vnd,
    -- Position sizing score (0-25): Did we risk appropriate amount?
    CASE
        WHEN t.buy_total_vnd BETWEEN 10000000 AND 27000000 THEN 25  -- Within proper range
        WHEN t.buy_total_vnd < 10000000 THEN 15  -- Too small
        ELSE 10  -- Too large
    END AS sizing_score,
    -- Holding discipline score (0-25): Swing = 7-30 days ideal
    CASE
        WHEN t.exit_date - t.entry_date BETWEEN 7 AND 30 THEN 25
        WHEN t.exit_date - t.entry_date BETWEEN 3 AND 45 THEN 15
        ELSE 5
    END AS hold_score,
    -- Win/Loss score (0-50)
    CASE
        WHEN t.pl_pct > 0.10 THEN 50  -- >10% win
        WHEN t.pl_pct > 0.05 THEN 40  -- 5-10% win
        WHEN t.pl_pct > 0 THEN 30     -- Small win
        WHEN t.pl_pct > -0.03 THEN 20 -- Small loss (good stop)
        WHEN t.pl_pct > -0.05 THEN 10 -- Medium loss
        ELSE 0                         -- Large loss
    END AS result_score,
    -- Total quality score (0-100)
    CASE
        WHEN t.buy_total_vnd BETWEEN 10000000 AND 27000000 THEN 25
        WHEN t.buy_total_vnd < 10000000 THEN 15
        ELSE 10
    END +
    CASE
        WHEN t.exit_date - t.entry_date BETWEEN 7 AND 30 THEN 25
        WHEN t.exit_date - t.entry_date BETWEEN 3 AND 45 THEN 15
        ELSE 5
    END +
    CASE
        WHEN t.pl_pct > 0.10 THEN 50
        WHEN t.pl_pct > 0.05 THEN 40
        WHEN t.pl_pct > 0 THEN 30
        WHEN t.pl_pct > -0.03 THEN 20
        WHEN t.pl_pct > -0.05 THEN 10
        ELSE 0
    END AS quality_score
FROM trades_calculated t
WHERE t.status = 'CLOSED' AND t.exit_date IS NOT NULL
ORDER BY t.exit_date DESC;


-- 17. v_sector_performance - By Sector
DROP VIEW IF EXISTS v_sector_performance CASCADE;
CREATE VIEW v_sector_performance AS
SELECT
    COALESCE(s.display_name, 'Unknown') AS sector,
    COUNT(*) AS trades,
    SUM(CASE WHEN t.pl_net_vnd > 0 THEN 1 ELSE 0 END) AS wins,
    ROUND(SUM(CASE WHEN t.pl_net_vnd > 0 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) AS win_rate,
    SUM(t.pl_net_vnd) AS total_pl_vnd,
    (
        SELECT t2.ticker
        FROM trades_calculated t2
        LEFT JOIN stocks st2 ON t2.ticker = st2.ticker
        WHERE st2.sector_id = s.id AND t2.status = 'CLOSED'
        GROUP BY t2.ticker
        ORDER BY SUM(t2.pl_net_vnd) DESC
        LIMIT 1
    ) AS best_ticker
FROM trades_calculated t
LEFT JOIN stocks st ON t.ticker = st.ticker
LEFT JOIN sectors s ON st.sector_id = s.id
WHERE t.status = 'CLOSED'
GROUP BY s.id, s.display_name
ORDER BY total_pl_vnd DESC;


-- 18. v_recent_trades - Last N Trades (most recent 20)
DROP VIEW IF EXISTS v_recent_trades CASCADE;
CREATE VIEW v_recent_trades AS
SELECT
    t.id,
    t.ticker,
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


-- 19. v_open_positions - Current Holdings with P/L
DROP VIEW IF EXISTS v_open_positions CASCADE;
CREATE VIEW v_open_positions AS
SELECT
    p.ticker,
    p.holding_type,
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
    WHERE ticker = p.ticker AND status = 'OPEN'
    ORDER BY entry_date DESC
    LIMIT 1
) t ON true
WHERE p.holding_type != 'Cash' AND p.shares > 0
ORDER BY p.market_value_vnd DESC;


-- =====================================================
-- GRANTS (for Data API access)
-- =====================================================
-- Note: Run these after creating a dedicated API user if needed
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_user;
-- GRANT SELECT ON v_swing_metrics, v_metrics_by_strategy, ... TO api_user;
