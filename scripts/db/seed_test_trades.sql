-- =====================================================
-- SEED DATA: Test Trades for Metrics Views
-- =====================================================
-- Creates realistic test data to verify all 19 views
-- Mix of wins/losses, strategies, sectors, time periods
-- =====================================================

-- Clear existing test data (be careful in production!)
TRUNCATE trades_calculated CASCADE;
TRUNCATE portfolio_holdings CASCADE;
TRUNCATE goals CASCADE;
TRUNCATE stocks CASCADE;
TRUNCATE sectors CASCADE;

-- Re-insert sectors
INSERT INTO sectors (id, name, display_name) VALUES
    (1, 'banking', 'Banking'),
    (2, 'real_estate', 'Real Estate'),
    (3, 'technology', 'Technology'),
    (4, 'state_owned', 'State-Owned'),
    (5, 'consumer', 'Consumer'),
    (6, 'infrastructure', 'Infrastructure'),
    (7, 'securities', 'Securities');

-- Insert test stocks
INSERT INTO stocks (ticker, company_name, sector_id, stock_type) VALUES
    ('TCB', 'Techcombank', 1, 'Private'),
    ('VCB', 'Vietcombank', 1, 'State'),
    ('FPT', 'FPT Corporation', 3, 'Private'),
    ('VHM', 'Vinhomes', 2, 'Vingroup'),
    ('NLG', 'Nam Long Group', 2, 'Private'),
    ('HPG', 'Hoa Phat Group', 6, 'Private'),
    ('MWG', 'Mobile World', 3, 'Retail'),
    ('GAS', 'PV Gas', 4, 'State'),
    ('SAB', 'Sabeco', 5, 'Beverages'),
    ('SSI', 'SSI Securities', 3, 'Securities');

-- =====================================================
-- CLOSED TRADES (for metrics calculation)
-- =====================================================
-- Mix of strategies, win/loss, different holding periods

INSERT INTO trades_calculated (
    ticker, entry_date, entry_price_vnd, shares, exit_date, exit_price_vnd,
    strategy, status, buy_total_vnd, sell_total_vnd, pl_gross_vnd, pl_pct, transaction_cost_vnd, pl_net_vnd
) VALUES
    -- Big wins (Trend strategy)
    ('TCB', '2025-11-01', 33000, 500, '2025-11-20', 38500, 'Trend', 'CLOSED',
     16500000, 19250000, 2750000, 0.1667, 107250, 2642750),
    ('FPT', '2025-11-05', 92000, 200, '2025-11-25', 108000, 'Trend', 'CLOSED',
     18400000, 21600000, 3200000, 0.1739, 120000, 3080000),
    ('VHM', '2025-12-01', 42000, 400, '2025-12-18', 48000, 'Breakout', 'CLOSED',
     16800000, 19200000, 2400000, 0.1429, 108000, 2292000),

    -- Medium wins (Bounce strategy)
    ('NLG', '2025-11-10', 31000, 600, '2025-11-28', 34500, 'Bounce', 'CLOSED',
     18600000, 20700000, 2100000, 0.1129, 117900, 1982100),
    ('HPG', '2025-12-05', 26000, 700, '2025-12-22', 28500, 'Bounce', 'CLOSED',
     18200000, 19950000, 1750000, 0.0962, 114450, 1635550),
    ('SSI', '2025-12-10', 28000, 500, '2025-12-28', 30000, 'Trend', 'CLOSED',
     14000000, 15000000, 1000000, 0.0714, 87000, 913000),

    -- Small wins
    ('MWG', '2025-12-15', 52000, 300, '2026-01-05', 54000, 'Divergence', 'CLOSED',
     15600000, 16200000, 600000, 0.0385, 95400, 504600),
    ('GAS', '2025-12-20', 78000, 200, '2026-01-08', 80500, 'Bounce', 'CLOSED',
     15600000, 16100000, 500000, 0.0321, 95100, 404900),

    -- Small losses (good stops)
    ('VCB', '2025-11-15', 88000, 200, '2025-11-22', 85500, 'Breakout', 'CLOSED',
     17600000, 17100000, -500000, -0.0284, 104100, -604100),
    ('SAB', '2025-12-01', 68000, 250, '2025-12-10', 65500, 'Trend', 'CLOSED',
     17000000, 16375000, -625000, -0.0368, 100125, -725125),

    -- Medium losses
    ('TCB', '2025-12-15', 37000, 450, '2025-12-28', 34000, 'Divergence', 'CLOSED',
     16650000, 15300000, -1350000, -0.0811, 95850, -1445850),

    -- 2026 January trades (recent)
    ('FPT', '2026-01-02', 105000, 180, '2026-01-15', 112000, 'Trend', 'CLOSED',
     18900000, 20160000, 1260000, 0.0667, 117180, 1142820),
    ('NLG', '2026-01-05', 33000, 550, '2026-01-20', 36000, 'Bounce', 'CLOSED',
     18150000, 19800000, 1650000, 0.0909, 113850, 1536150),
    ('VHM', '2026-01-08', 46000, 350, '2026-01-22', 44500, 'Breakout', 'CLOSED',
     16100000, 15575000, -525000, -0.0326, 95025, -620025),
    ('HPG', '2026-01-10', 27500, 600, '2026-01-25', 29500, 'Trend', 'CLOSED',
     16500000, 17700000, 1200000, 0.0727, 102600, 1097400);

-- =====================================================
-- OPEN TRADES (for position alerts)
-- =====================================================

INSERT INTO trades_calculated (
    ticker, entry_date, entry_price_vnd, shares, exit_date, exit_price_vnd,
    strategy, status, buy_total_vnd, sell_total_vnd, pl_gross_vnd, pl_pct, transaction_cost_vnd, pl_net_vnd
) VALUES
    -- Open position - doing well
    ('SSI', '2026-01-15', 29500, 400, NULL, NULL, 'Bounce', 'OPEN',
     11800000, 0, 0, 0, 0, 0),
    -- Open position - underwater
    ('MWG', '2026-01-18', 55000, 280, NULL, NULL, 'Divergence', 'OPEN',
     15400000, 0, 0, 0, 0, 0);

-- =====================================================
-- PORTFOLIO HOLDINGS
-- =====================================================

INSERT INTO portfolio_holdings (ticker, holding_type, shares, avg_cost_vnd, current_price_vnd) VALUES
    ('SSI', 'Stock', 400, 29500, 31500),      -- Open position, slight gain
    ('MWG', 'Stock', 280, 55000, 48000),      -- Open position, underwater
    ('Cash', 'Cash', 42000000, 1, 1);          -- Cash balance (stored in shares as VND)

-- =====================================================
-- GOALS
-- =====================================================

INSERT INTO goals (name, target_vnd, realized_vnd, start_date, deadline, status, goal_type) VALUES
    ('January 2026 Target', 3000000, 2156320, '2026-01-01', '2026-01-31', 'Active', 'Monthly'),
    ('Q1 2026 Target', 10000000, 2156320, '2026-01-01', '2026-03-31', 'Active', 'Quarterly');

-- =====================================================
-- VERIFY DATA
-- =====================================================

-- Check counts
SELECT 'trades_calculated' AS table_name, COUNT(*) AS row_count FROM trades_calculated
UNION ALL SELECT 'portfolio_holdings', COUNT(*) FROM portfolio_holdings
UNION ALL SELECT 'goals', COUNT(*) FROM goals
UNION ALL SELECT 'stocks', COUNT(*) FROM stocks
UNION ALL SELECT 'sectors', COUNT(*) FROM sectors;

-- Quick metrics check
SELECT
    COUNT(*) AS total_trades,
    SUM(CASE WHEN pl_net_vnd > 0 THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN pl_net_vnd < 0 THEN 1 ELSE 0 END) AS losses,
    SUM(pl_net_vnd) AS total_pl
FROM trades_calculated
WHERE status = 'CLOSED';
