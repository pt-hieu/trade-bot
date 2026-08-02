-- Migration 017: Database optimization and postgres.md compliance
-- Safe to re-run (all statements are idempotent)
--
-- Strategy: Views depend on varchar columns, so we must:
--   1. Drop all views
--   2. ALTER varchar → text
--   3. Recreate all views
--   4. Index changes

-- ============================================================
-- 1. Enable pg_stat_statements for slow query monitoring
-- ============================================================
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- ============================================================
-- 2. Drop ALL views (required before ALTER TYPE on columns)
-- ============================================================
-- Dependent views first (they reference other views)
DROP VIEW IF EXISTS v_metric_alerts CASCADE;
DROP VIEW IF EXISTS v_open_positions CASCADE;

-- Independent views
DROP VIEW IF EXISTS v_capital_efficiency CASCADE;
DROP VIEW IF EXISTS v_goal_progress CASCADE;
DROP VIEW IF EXISTS v_holding_analysis CASCADE;
DROP VIEW IF EXISTS v_latest_technicals CASCADE;
DROP VIEW IF EXISTS v_longterm_alerts CASCADE;
DROP VIEW IF EXISTS v_longterm_allocation CASCADE;
DROP VIEW IF EXISTS v_longterm_entry_zones CASCADE;
DROP VIEW IF EXISTS v_longterm_metrics CASCADE;
DROP VIEW IF EXISTS v_longterm_monthly CASCADE;
DROP VIEW IF EXISTS v_longterm_positions CASCADE;
DROP VIEW IF EXISTS v_longterm_watchlist CASCADE;
DROP VIEW IF EXISTS v_metrics_by_strategy CASCADE;
DROP VIEW IF EXISTS v_metrics_by_ticker CASCADE;
DROP VIEW IF EXISTS v_metrics_mom CASCADE;
DROP VIEW IF EXISTS v_metrics_monthly CASCADE;
DROP VIEW IF EXISTS v_metrics_weekly CASCADE;
DROP VIEW IF EXISTS v_metrics_wow CASCADE;
DROP VIEW IF EXISTS v_portfolio_current CASCADE;
DROP VIEW IF EXISTS v_portfolio_value_history CASCADE;
DROP VIEW IF EXISTS v_position_alerts CASCADE;
DROP VIEW IF EXISTS v_recent_trades CASCADE;
DROP VIEW IF EXISTS v_risk_metrics CASCADE;
DROP VIEW IF EXISTS v_rolling_performance CASCADE;
DROP VIEW IF EXISTS v_sector_performance CASCADE;
DROP VIEW IF EXISTS v_streak_analysis CASCADE;
DROP VIEW IF EXISTS v_swing_metrics CASCADE;
DROP VIEW IF EXISTS v_swing_positions CASCADE;
DROP VIEW IF EXISTS v_swing_watchlist CASCADE;
DROP VIEW IF EXISTS v_trade_performance CASCADE;
DROP VIEW IF EXISTS v_trade_quality CASCADE;

-- ============================================================
-- 3. Convert varchar columns to text (metadata-only, no rewrite)
-- Per postgres.md: use text, not varchar
-- ============================================================

-- daily_prices
ALTER TABLE daily_prices ALTER COLUMN ticker TYPE text;

-- daily_technicals
ALTER TABLE daily_technicals ALTER COLUMN ticker TYPE text;
ALTER TABLE daily_technicals ALTER COLUMN price_vs_ma20 TYPE text;
ALTER TABLE daily_technicals ALTER COLUMN price_vs_ma50 TYPE text;

-- daily_levels
ALTER TABLE daily_levels ALTER COLUMN ticker TYPE text;

-- daily_evaluations
ALTER TABLE daily_evaluations ALTER COLUMN ticker TYPE text;

-- daily_recommendations
ALTER TABLE daily_recommendations ALTER COLUMN ticker TYPE text;
ALTER TABLE daily_recommendations ALTER COLUMN section TYPE text;

-- daily_scans
ALTER TABLE daily_scans ALTER COLUMN status TYPE text;

-- articles
ALTER TABLE articles ALTER COLUMN domain TYPE text;

-- article_searches
ALTER TABLE article_searches ALTER COLUMN query_name TYPE text;
ALTER TABLE article_searches ALTER COLUMN status TYPE text;

-- trades_calculated
ALTER TABLE trades_calculated ALTER COLUMN ticker TYPE text;

-- portfolio_holdings
ALTER TABLE portfolio_holdings ALTER COLUMN ticker TYPE text;

-- swing_watchlist
ALTER TABLE swing_watchlist ALTER COLUMN ticker TYPE text;

-- longterm_watchlist
ALTER TABLE longterm_watchlist ALTER COLUMN ticker TYPE text;

-- stocks
ALTER TABLE stocks ALTER COLUMN ticker TYPE text;
ALTER TABLE stocks ALTER COLUMN company_name TYPE text;
ALTER TABLE stocks ALTER COLUMN exchange TYPE text;

-- sectors
ALTER TABLE sectors ALTER COLUMN name TYPE text;
ALTER TABLE sectors ALTER COLUMN display_name TYPE text;

-- foreign_flow_details
ALTER TABLE foreign_flow_details ALTER COLUMN ticker TYPE text;
ALTER TABLE foreign_flow_details ALTER COLUMN flow_type TYPE text;

-- midday_big_movers
ALTER TABLE midday_big_movers ALTER COLUMN ticker TYPE text;
ALTER TABLE midday_big_movers ALTER COLUMN direction TYPE text;

-- midday_entries_hit
ALTER TABLE midday_entries_hit ALTER COLUMN ticker TYPE text;

-- midday_position_alerts
ALTER TABLE midday_position_alerts ALTER COLUMN ticker TYPE text;
ALTER TABLE midday_position_alerts ALTER COLUMN level_type TYPE text;

-- trade_entries
ALTER TABLE trade_entries ALTER COLUMN ticker TYPE text;

-- goals
ALTER TABLE goals ALTER COLUMN name TYPE text;

-- learning_patterns
ALTER TABLE learning_patterns ALTER COLUMN pattern_type TYPE text;

-- trading_rules
ALTER TABLE trading_rules ALTER COLUMN rule_name TYPE text;
ALTER TABLE trading_rules ALTER COLUMN rule_type TYPE text;

-- sync_log
ALTER TABLE sync_log ALTER COLUMN source TYPE text;
ALTER TABLE sync_log ALTER COLUMN status TYPE text;
ALTER TABLE sync_log ALTER COLUMN sync_type TYPE text;
ALTER TABLE sync_log ALTER COLUMN table_name TYPE text;

-- ticker_insights
ALTER TABLE ticker_insights ALTER COLUMN ticker TYPE text;

-- macro_events
ALTER TABLE macro_events ALTER COLUMN event_name TYPE text;

-- sector_rotation_details
ALTER TABLE sector_rotation_details ALTER COLUMN classification TYPE text;

-- ============================================================
-- 4. Drop legacy notion_page_id columns (Notion removed in 51f5ee2)
-- ============================================================
ALTER TABLE portfolio_holdings DROP COLUMN IF EXISTS notion_page_id;
ALTER TABLE swing_watchlist DROP COLUMN IF EXISTS notion_page_id;
ALTER TABLE longterm_watchlist DROP COLUMN IF EXISTS notion_page_id;
ALTER TABLE trade_entries DROP COLUMN IF EXISTS notion_page_id;
ALTER TABLE goals DROP COLUMN IF EXISTS notion_page_id;

-- ============================================================
-- 5. Recreate ALL views (dependency order)
-- ============================================================

-- --- schema.sql base views ---

CREATE VIEW v_portfolio_current AS
SELECT
    h.ticker,
    h.holding_type,
    h.shares,
    h.avg_cost_vnd,
    h.current_price_vnd,
    h.cost_basis_vnd,
    h.market_value_vnd,
    (h.market_value_vnd - h.cost_basis_vnd) AS pl_vnd,
    CASE WHEN h.cost_basis_vnd > 0
         THEN ((h.market_value_vnd - h.cost_basis_vnd)::DECIMAL / h.cost_basis_vnd * 100)
         ELSE 0
    END AS pl_pct,
    s.name AS sector_name
FROM portfolio_holdings h
LEFT JOIN stocks st ON h.ticker = st.ticker
LEFT JOIN sectors s ON st.sector_id = s.id
WHERE h.shares > 0 OR h.holding_type = 'Cash';

CREATE VIEW v_latest_technicals AS
SELECT
    t.ticker,
    t.scan_date,
    t.rsi,
    t.macd,
    t.macd_signal,
    t.trend,
    t.trend_strength,
    t.momentum,
    t.pattern,
    t.pattern_signal,
    t.analysis,
    l.swing_high_vnd,
    l.swing_low_vnd,
    l.nearest_support_vnd,
    l.nearest_resistance_vnd,
    p.close_vnd AS current_price_vnd
FROM daily_technicals t
JOIN daily_levels l ON t.scan_date = l.scan_date AND t.ticker = l.ticker
JOIN daily_prices p ON t.scan_date = p.scan_date AND t.ticker = p.ticker
WHERE t.scan_date = (SELECT MAX(scan_date) FROM daily_scans);

CREATE VIEW v_trade_performance AS
SELECT
    ticker,
    COUNT(*) AS total_trades,
    SUM(CASE WHEN pl_gross_vnd > 0 THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN pl_gross_vnd < 0 THEN 1 ELSE 0 END) AS losses,
    SUM(pl_gross_vnd) AS total_pl_gross_vnd,
    SUM(pl_net_vnd) AS total_pl_net_vnd,
    AVG(pl_pct) AS avg_pl_pct,
    MAX(entry_date) AS last_trade_date
FROM trades_calculated
WHERE status = 'CLOSED'
GROUP BY ticker;

CREATE VIEW v_swing_watchlist AS
SELECT
    sw.ticker,
    s.name AS sector,
    s.display_name AS sector_display,
    sw.stock_type,
    sw.rsi,
    sw.notes,
    sw.is_active
FROM swing_watchlist sw
JOIN sectors s ON sw.sector_id = s.id
WHERE sw.is_active = TRUE;

CREATE VIEW v_longterm_watchlist AS
SELECT
    lw.ticker,
    s.name AS sector,
    s.display_name AS sector_display,
    lw.entry_zone_vnd,
    lw.conviction,
    lw.pe_ratio,
    lw.roe,
    lw.dividend_yield,
    lw.tier,
    lw.notes,
    lw.is_active
FROM longterm_watchlist lw
JOIN sectors s ON lw.sector_id = s.id
WHERE lw.is_active = TRUE;

-- --- migration 008 views (not overridden by 010) ---

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
    ROUND(max_drawdown_vnd::NUMERIC / NULLIF(10000000, 0) * 100, 2) AS max_drawdown_pct,
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

CREATE VIEW v_holding_analysis AS
SELECT
    ROUND(AVG(CASE WHEN pl_net_vnd > 0 THEN exit_date - entry_date END)::NUMERIC, 1) AS avg_hold_winners,
    ROUND(AVG(CASE WHEN pl_net_vnd < 0 THEN exit_date - entry_date END)::NUMERIC, 1) AS avg_hold_losers,
    SUM(CASE WHEN exit_date - entry_date < 7 THEN 1 ELSE 0 END) AS early_exits,
    SUM(CASE WHEN exit_date - entry_date > 30 THEN 1 ELSE 0 END) AS extended_holds,
    COUNT(*) AS total_closed_trades
FROM trades_calculated
WHERE status = 'CLOSED' AND exit_date IS NOT NULL;

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

CREATE VIEW v_trade_quality AS
SELECT
    t.id,
    t.ticker,
    t.entry_date,
    t.exit_date,
    t.pl_pct,
    t.pl_net_vnd,
    CASE
        WHEN t.buy_total_vnd BETWEEN 10000000 AND 27000000 THEN 25
        WHEN t.buy_total_vnd < 10000000 THEN 15
        ELSE 10
    END AS sizing_score,
    CASE
        WHEN t.exit_date - t.entry_date BETWEEN 7 AND 30 THEN 25
        WHEN t.exit_date - t.entry_date BETWEEN 3 AND 45 THEN 15
        ELSE 5
    END AS hold_score,
    CASE
        WHEN t.pl_pct > 0.10 THEN 50
        WHEN t.pl_pct > 0.05 THEN 40
        WHEN t.pl_pct > 0 THEN 30
        WHEN t.pl_pct > -0.03 THEN 20
        WHEN t.pl_pct > -0.05 THEN 10
        ELSE 0
    END AS result_score,
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
    SELECT
        ticker,
        'STALE' AS alert_type,
        days_held,
        pl_pct AS current_pl_pct,
        'Position held ' || days_held || ' days with only ' || pl_pct || '% gain. Consider exit.' AS message
    FROM position_data
    WHERE days_held > 30 AND pl_pct < 5

    UNION ALL

    SELECT
        ticker,
        'UNDERWATER',
        days_held,
        pl_pct,
        'Position down ' || ABS(pl_pct) || '%. Review stop-loss.' AS message
    FROM position_data
    WHERE pl_pct < -10

    UNION ALL

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

-- --- migration 010 views ---

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
    SELECT
        p.ticker,
        'OVERWEIGHT' AS alert_type,
        ROUND(p.market_value_vnd::NUMERIC / NULLIF(t.total_value, 0) * 100, 1) AS current_value,
        'Position is ' || ROUND(p.market_value_vnd::NUMERIC / NULLIF(t.total_value, 0) * 100, 1) || '% of portfolio. Consider trimming.' AS message
    FROM position_data p, total t
    WHERE p.market_value_vnd::NUMERIC / NULLIF(t.total_value, 0) > 0.40

    UNION ALL

    SELECT
        ticker,
        'BIG_GAINER',
        ROUND(pl_pct, 1),
        'Position up ' || ROUND(pl_pct, 1) || '%. Consider trimming to lock in gains.'
    FROM position_data
    WHERE pl_pct > 50

    UNION ALL

    SELECT
        ticker,
        'BACK_IN_ZONE',
        current_price_vnd,
        'Price returned to entry zone (' || entry_zone_vnd || '). Consider adding.'
    FROM position_data
    WHERE entry_zone_vnd IS NOT NULL AND current_price_vnd <= entry_zone_vnd
) alerts
ORDER BY alert_type, ticker;

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

-- --- migration 012 view (latest v_recent_trades) ---

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

-- --- migration 016 view (v_portfolio_value_history) ---

CREATE VIEW v_portfolio_value_history AS
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

-- --- Dependent views (must come after their dependencies) ---

-- v_open_positions depends on v_swing_positions
CREATE VIEW v_open_positions AS
SELECT * FROM v_swing_positions;

-- v_metric_alerts depends on v_swing_metrics, v_streak_analysis, v_risk_metrics
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
    SELECT
        CASE WHEN m.win_rate < 40 THEN 'CRITICAL' ELSE 'WARNING' END AS alert_type,
        'Win Rate' AS metric,
        m.win_rate AS current_value,
        '50-100%' AS threshold,
        'Win rate is ' || ROUND(m.win_rate, 1) || '%, below healthy range' AS message
    FROM metrics m
    WHERE m.win_rate < 50

    UNION ALL

    SELECT
        CASE WHEN m.profit_factor < 1.0 THEN 'CRITICAL' ELSE 'WARNING' END,
        'Profit Factor',
        m.profit_factor,
        '>1.5',
        'Profit factor is ' || m.profit_factor || ', edge is weak'
    FROM metrics m
    WHERE m.profit_factor IS NOT NULL AND m.profit_factor < 1.5

    UNION ALL

    SELECT
        CASE WHEN m.expectancy_vnd < 0 THEN 'CRITICAL' ELSE 'WARNING' END,
        'Expectancy',
        m.expectancy_vnd,
        '>500K VND',
        'Expectancy is ' || COALESCE(m.expectancy_vnd::TEXT, '0') || ' VND'
    FROM metrics m
    WHERE m.expectancy_vnd IS NOT NULL AND m.expectancy_vnd < 500000

    UNION ALL

    SELECT
        CASE WHEN r.max_drawdown_pct < -20 THEN 'CRITICAL' ELSE 'WARNING' END,
        'Max Drawdown',
        r.max_drawdown_pct,
        '<10%',
        'Drawdown is ' || ABS(COALESCE(r.max_drawdown_pct, 0)) || '% of capital'
    FROM risk r
    WHERE r.max_drawdown_pct IS NOT NULL AND r.max_drawdown_pct < -10

    UNION ALL

    SELECT
        CASE WHEN m.avg_holding_days > 60 THEN 'CRITICAL' ELSE 'WARNING' END,
        'Avg Holding Period',
        m.avg_holding_days,
        '<45 days',
        'Average hold is ' || COALESCE(m.avg_holding_days::TEXT, '0') || ' days, too long for swing'
    FROM metrics m
    WHERE m.avg_holding_days IS NOT NULL AND m.avg_holding_days > 45

    UNION ALL

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

-- ============================================================
-- 6. Add indexes on unindexed foreign keys
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks (sector_id);
CREATE INDEX IF NOT EXISTS idx_rotation_details_sector ON sector_rotation_details (sector_id);
CREATE INDEX IF NOT EXISTS idx_mode_violations_record ON mode_violations (record_id);
CREATE INDEX IF NOT EXISTS idx_rotation_returns_eval ON rotation_sector_returns (rotation_eval_id);
CREATE INDEX IF NOT EXISTS idx_rotation_returns_sector ON rotation_sector_returns (sector_id);
CREATE INDEX IF NOT EXISTS idx_rules_pattern ON trading_rules (derived_from_pattern_id);

-- ============================================================
-- 7. Drop redundant/unused indexes
-- ============================================================
DROP INDEX IF EXISTS idx_levels_ticker;
DROP INDEX IF EXISTS idx_tech_ticker;
DROP INDEX IF EXISTS idx_prices_ticker;
DROP INDEX IF EXISTS idx_tech_atr;
DROP INDEX IF EXISTS idx_tech_adx;
DROP INDEX IF EXISTS idx_tech_volume_vs_avg;
DROP INDEX IF EXISTS idx_tech_closed_at_low;
DROP INDEX IF EXISTS idx_tech_supertrend_dir;
DROP INDEX IF EXISTS idx_scan_date;
DROP INDEX IF EXISTS idx_regime_type;
DROP INDEX IF EXISTS idx_swing_rsi;

-- ============================================================
-- 8. Add composite indexes matching actual query patterns
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_trades_status_date ON trades_calculated (status, entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_eval_record_ticker ON daily_evaluations (record_id, ticker);
CREATE INDEX IF NOT EXISTS idx_rec_record_action ON daily_recommendations (record_id, action);

-- ============================================================
-- 9. Replace B-tree with BRIN on time-series date columns
-- ============================================================
DROP INDEX IF EXISTS idx_prices_date;
CREATE INDEX IF NOT EXISTS idx_prices_date_brin ON daily_prices USING brin (scan_date);

DROP INDEX IF EXISTS idx_tech_date;
CREATE INDEX IF NOT EXISTS idx_tech_date_brin ON daily_technicals USING brin (scan_date);
