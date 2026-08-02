-- =====================================================
-- SWINGY TRADING SYSTEM - PostgreSQL SCHEMA FOR NEON
-- =====================================================
-- Version: 1.0.0
-- Created: 2026-01-31
-- Description: Full schema for migrating from Notion + local JSON to Neon

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =====================================================
-- ENUMS (Controlled Values)
-- =====================================================

-- Trade status
CREATE TYPE trade_status AS ENUM ('OPEN', 'CLOSED', 'CANCELLED', 'PARTIAL');

-- Trading strategies
CREATE TYPE trading_strategy AS ENUM ('Bounce', 'Trend', 'Breakout', 'Divergence');

-- Market regimes
CREATE TYPE market_regime AS ENUM ('RISK_ON', 'RISK_OFF', 'NEUTRAL');

-- Global risk regimes
CREATE TYPE global_risk_regime AS ENUM ('CALM', 'CAUTIOUS', 'ELEVATED', 'CRISIS');

-- DXY signals
CREATE TYPE dxy_signal AS ENUM ('WEAK', 'NEUTRAL', 'STRONG');

-- VIX signals
CREATE TYPE vix_signal AS ENUM ('LOW', 'MODERATE', 'HIGH', 'EXTREME');

-- USD/VND signals
CREATE TYPE usd_vnd_signal AS ENUM ('STABLE', 'PRESSURE', 'FLIGHT');

-- Trend directions
CREATE TYPE trend_direction AS ENUM ('UPTREND', 'DOWNTREND', 'SIDEWAYS');

-- Trend strength
CREATE TYPE trend_strength AS ENUM ('strong', 'moderate', 'weak');

-- Momentum
CREATE TYPE momentum_type AS ENUM ('bullish', 'neutral', 'bearish');

-- Candlestick patterns
CREATE TYPE candle_pattern AS ENUM ('hammer', 'inverted_hammer', 'doji', 'bullish_engulfing', 'bearish_engulfing');

-- Pattern signals
CREATE TYPE pattern_signal AS ENUM ('bullish_reversal', 'bearish_reversal', 'indecision');

-- Recommendation actions
CREATE TYPE rec_action AS ENUM ('BUY', 'SELL', 'HOLD', 'WATCH', 'WAIT', 'SKIP', 'AVOID', 'LIMIT_BUY', 'EXIT', 'TRIM', 'ADD');

-- Evaluation status
CREATE TYPE eval_status AS ENUM ('WIN', 'LOSS', 'PENDING', 'MISSED', 'HOLD', 'WATCH', 'WAIT', 'EXIT', 'MISS');

-- Trading modes
CREATE TYPE trading_mode AS ENUM ('NORMAL', 'LOW_CASH', 'REALLOCATION');

-- Goal status
CREATE TYPE goal_status AS ENUM ('Active', 'Achieved', 'Failed', 'Paused', 'Tracking');

-- Goal type
CREATE TYPE goal_type AS ENUM ('Monthly', 'Quarterly', 'Yearly', 'Custom');

-- Holding types
CREATE TYPE holding_type AS ENUM ('Stock', 'ETF', 'Cash');

-- Stock types for watchlist
CREATE TYPE stock_type AS ENUM (
    'Private', 'State', 'Industrial', 'Vingroup', 'Retail', 'Securities',
    'Conglomerate', 'Energy', 'Commodities', 'Aviation', 'Insurance',
    'Beverages', 'Dairy', 'Logistics', 'Steel'
);

-- Conviction levels
CREATE TYPE conviction_level AS ENUM ('High', 'Medium-High', 'Medium', 'Medium-Low', 'Low');

-- Foreign flow signals
CREATE TYPE flow_signal AS ENUM ('RISK_ON', 'RISK_OFF', 'NEUTRAL');

-- Flow patterns
CREATE TYPE flow_pattern AS ENUM ('Accumulation', 'Distribution', 'Neutral');

-- Sector bias
CREATE TYPE sector_bias AS ENUM ('hot', 'cold', 'neutral', 'bullish', 'bearish');

-- =====================================================
-- CORE REFERENCE TABLES
-- =====================================================

-- Sectors (reference table)
CREATE TABLE sectors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default sectors
INSERT INTO sectors (name, display_name) VALUES
    ('banking', 'Banking'),
    ('real_estate', 'Real Estate'),
    ('technology', 'Technology'),
    ('state_owned', 'State-Owned'),
    ('consumer', 'Consumer'),
    ('infrastructure', 'Infrastructure');

-- Stocks (master table for all tickers)
CREATE TABLE stocks (
    ticker VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(200),
    sector_id INTEGER REFERENCES sectors(id),
    stock_type stock_type,
    exchange VARCHAR(10) DEFAULT 'HOSE',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- 1. PORTFOLIO HOLDINGS (from Notion)
-- =====================================================

CREATE TABLE portfolio_holdings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker VARCHAR(10) NOT NULL,
    holding_type holding_type NOT NULL DEFAULT 'Stock',
    shares INTEGER NOT NULL DEFAULT 0,
    avg_cost_vnd BIGINT NOT NULL DEFAULT 0,  -- Raw VND, not thousands
    current_price_vnd BIGINT,

    -- Computed columns
    cost_basis_vnd BIGINT GENERATED ALWAYS AS (shares * avg_cost_vnd) STORED,
    market_value_vnd BIGINT GENERATED ALWAYS AS (shares * COALESCE(current_price_vnd, avg_cost_vnd)) STORED,

    notion_page_id VARCHAR(50),  -- For backwards compatibility during migration
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for quick lookups
CREATE INDEX idx_portfolio_ticker ON portfolio_holdings(ticker);
CREATE INDEX idx_portfolio_type ON portfolio_holdings(holding_type);

-- =====================================================
-- 2. TRADES (from Notion)
-- =====================================================

-- Trades (source of truth for all trade data)
CREATE TABLE trades_calculated (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker VARCHAR(10) NOT NULL,
    entry_date DATE NOT NULL,
    entry_price_vnd BIGINT NOT NULL,
    shares INTEGER NOT NULL,
    exit_date DATE,
    exit_price_vnd BIGINT,
    strategy trading_strategy,
    status trade_status NOT NULL,

    -- Calculated P/L fields
    buy_total_vnd BIGINT NOT NULL,
    sell_total_vnd BIGINT DEFAULT 0,
    pl_gross_vnd BIGINT DEFAULT 0,
    pl_pct DECIMAL(8, 4) DEFAULT 0,  -- Percentage with 4 decimals
    transaction_cost_vnd BIGINT DEFAULT 0,  -- ~0.3% round trip
    pl_net_vnd BIGINT DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for trade queries
CREATE INDEX idx_trades_calc_ticker ON trades_calculated(ticker);
CREATE INDEX idx_trades_calc_status ON trades_calculated(status);
CREATE INDEX idx_trades_calc_date ON trades_calculated(entry_date DESC);

-- =====================================================
-- 3. SWING WATCHLIST (from Notion)
-- =====================================================

CREATE TABLE swing_watchlist (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker VARCHAR(10) NOT NULL UNIQUE,
    sector_id INTEGER NOT NULL REFERENCES sectors(id),
    stock_type stock_type,
    rsi DECIMAL(5, 2),  -- RSI value (0-100)
    notes TEXT,

    notion_page_id VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_swing_sector ON swing_watchlist(sector_id);
CREATE INDEX idx_swing_active ON swing_watchlist(is_active);
CREATE INDEX idx_swing_rsi ON swing_watchlist(rsi);

-- =====================================================
-- 4. LONG-TERM WATCHLIST (from Notion)
-- =====================================================

CREATE TABLE longterm_watchlist (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker VARCHAR(10) NOT NULL UNIQUE,
    sector_id INTEGER NOT NULL REFERENCES sectors(id),
    entry_zone_vnd BIGINT NOT NULL,  -- Raw VND
    conviction conviction_level DEFAULT 'Medium',
    pe_ratio DECIMAL(8, 2),
    roe DECIMAL(6, 2),
    dividend_yield DECIMAL(5, 2),
    tier INTEGER CHECK (tier >= 1 AND tier <= 3),  -- 1, 2, or 3
    research_file_path TEXT,
    notes TEXT,

    notion_page_id VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_longterm_conviction ON longterm_watchlist(conviction);
CREATE INDEX idx_longterm_sector ON longterm_watchlist(sector_id);
CREATE INDEX idx_longterm_tier ON longterm_watchlist(tier);

-- =====================================================
-- 5. GOALS (from Notion)
-- =====================================================

CREATE TABLE goals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(200) NOT NULL,
    target_vnd BIGINT NOT NULL,
    realized_vnd BIGINT DEFAULT 0,
    start_date DATE NOT NULL,
    deadline DATE NOT NULL,
    status goal_status DEFAULT 'Active',
    goal_type goal_type DEFAULT 'Monthly',
    notes TEXT,

    notion_page_id VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_goals_status ON goals(status);
CREATE INDEX idx_goals_deadline ON goals(deadline);

-- =====================================================
-- 6. DAILY SCANS (from JSON files)
-- =====================================================

-- Daily scan metadata
CREATE TABLE daily_scans (
    scan_date DATE PRIMARY KEY,
    status VARCHAR(20) DEFAULT 'success',
    watchlist_count INTEGER,
    prices_fetched INTEGER,
    articles_count INTEGER,
    errors JSONB,  -- Array of error messages
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scan_date ON daily_scans(scan_date DESC);

-- Daily prices (OHLCV)
CREATE TABLE daily_prices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_date DATE NOT NULL REFERENCES daily_scans(scan_date) ON DELETE CASCADE,
    ticker VARCHAR(10) NOT NULL,
    price_date DATE NOT NULL,
    open_vnd BIGINT NOT NULL,
    high_vnd BIGINT NOT NULL,
    low_vnd BIGINT NOT NULL,
    close_vnd BIGINT NOT NULL,
    volume BIGINT NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_price_scan_ticker UNIQUE (scan_date, ticker)
);

CREATE INDEX idx_prices_ticker ON daily_prices(ticker);
CREATE INDEX idx_prices_date ON daily_prices(scan_date DESC);

-- Daily technicals
CREATE TABLE daily_technicals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_date DATE NOT NULL REFERENCES daily_scans(scan_date) ON DELETE CASCADE,
    ticker VARCHAR(10) NOT NULL,

    -- RSI & MACD
    rsi DECIMAL(6, 2),
    macd DECIMAL(12, 4),
    macd_signal DECIMAL(12, 4),
    macd_histogram DECIMAL(12, 4),

    -- Moving Averages (raw VND)
    ma20_vnd BIGINT,
    ma50_vnd BIGINT,
    price_vs_ma20 VARCHAR(10),  -- 'above' or 'below'
    price_vs_ma50 VARCHAR(10),

    -- Trend analysis
    trend trend_direction,
    trend_strength trend_strength,
    momentum momentum_type,

    -- Pattern detection
    pattern candle_pattern,
    pattern_signal pattern_signal,

    -- Analysis text (generated by technicals.py)
    analysis TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_tech_scan_ticker UNIQUE (scan_date, ticker)
);

-- Support/Resistance levels (normalized from technicals)
CREATE TABLE daily_levels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_date DATE NOT NULL REFERENCES daily_scans(scan_date) ON DELETE CASCADE,
    ticker VARCHAR(10) NOT NULL,

    swing_high_vnd BIGINT,
    swing_high_date DATE,
    swing_low_vnd BIGINT,
    swing_low_date DATE,
    range_20d_high_vnd BIGINT,
    range_20d_low_vnd BIGINT,
    nearest_support_vnd BIGINT,
    nearest_resistance_vnd BIGINT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_levels_scan_ticker UNIQUE (scan_date, ticker)
);

CREATE INDEX idx_tech_ticker ON daily_technicals(ticker);
CREATE INDEX idx_tech_date ON daily_technicals(scan_date DESC);
CREATE INDEX idx_tech_rsi ON daily_technicals(rsi);
CREATE INDEX idx_levels_ticker ON daily_levels(ticker);

-- =====================================================
-- 7. MARKET REGIME (from market-level.json)
-- =====================================================

CREATE TABLE market_regimes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_date DATE NOT NULL UNIQUE REFERENCES daily_scans(scan_date) ON DELETE CASCADE,
    regime market_regime NOT NULL,
    regime_confidence DECIMAL(4, 2),  -- 0.00 to 1.00
    vn_index_value DECIMAL(10, 2),
    vn_index_change_pct DECIMAL(6, 2),
    key_signal TEXT,
    recommendation TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_regime_date ON market_regimes(scan_date DESC);
CREATE INDEX idx_regime_type ON market_regimes(regime);

-- =====================================================
-- 8. MACRO METRICS (from macro-metrics.json)
-- =====================================================

CREATE TABLE macro_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_date DATE NOT NULL UNIQUE REFERENCES daily_scans(scan_date) ON DELETE CASCADE,

    -- DXY (Dollar Index)
    dxy_value DECIMAL(8, 3),
    dxy_change_pct DECIMAL(6, 2),
    dxy_signal_value dxy_signal,

    -- VIX (Volatility Index)
    vix_value DECIMAL(6, 2),
    vix_change_pct DECIMAL(6, 2),
    vix_signal_value vix_signal,

    -- USD/VND Exchange
    usd_vnd_rate DECIMAL(10, 2),
    usd_vnd_signal_value usd_vnd_signal,

    -- Overall risk
    global_risk_regime global_risk_regime NOT NULL,
    interpretation TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Upcoming macro events (from macro-metrics.json)
CREATE TABLE macro_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_date DATE NOT NULL REFERENCES daily_scans(scan_date) ON DELETE CASCADE,
    event_name VARCHAR(200) NOT NULL,
    event_date DATE,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_macro_date ON macro_metrics(scan_date DESC);
CREATE INDEX idx_macro_regime ON macro_metrics(global_risk_regime);
CREATE INDEX idx_events_scan ON macro_events(scan_date);

-- =====================================================
-- 9. FOREIGN FLOW (from foreign-flow.json)
-- =====================================================

CREATE TABLE foreign_flows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_date DATE NOT NULL UNIQUE REFERENCES daily_scans(scan_date) ON DELETE CASCADE,

    net_value_billion DECIMAL(12, 2),
    buy_value_billion DECIMAL(12, 2),
    sell_value_billion DECIMAL(12, 2),

    signal flow_signal,
    pattern flow_pattern,
    interpretation TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Top bought/sold stocks
CREATE TABLE foreign_flow_details (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    flow_id UUID NOT NULL REFERENCES foreign_flows(id) ON DELETE CASCADE,
    ticker VARCHAR(10) NOT NULL,
    value_billion DECIMAL(12, 2) NOT NULL,
    flow_type VARCHAR(10) NOT NULL CHECK (flow_type IN ('bought', 'sold')),
    rank INTEGER NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_flow_date ON foreign_flows(scan_date DESC);
CREATE INDEX idx_flow_details_flow ON foreign_flow_details(flow_id);
CREATE INDEX idx_flow_details_ticker ON foreign_flow_details(ticker);

-- =====================================================
-- 10. SECTOR ROTATION (from sector-rotation.json)
-- =====================================================

CREATE TABLE sector_rotations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_date DATE NOT NULL UNIQUE REFERENCES daily_scans(scan_date) ON DELETE CASCADE,
    market_regime market_regime,
    market_avg_return DECIMAL(8, 4),
    rotation_signal TEXT,
    reasoning TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Hot/cold sector assignments
CREATE TABLE sector_rotation_details (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rotation_id UUID NOT NULL REFERENCES sector_rotations(id) ON DELETE CASCADE,
    sector_id INTEGER NOT NULL REFERENCES sectors(id),
    classification VARCHAR(10) NOT NULL CHECK (classification IN ('hot', 'cold')),
    return_pct DECIMAL(8, 4),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rotation_date ON sector_rotations(scan_date DESC);
CREATE INDEX idx_rotation_details ON sector_rotation_details(rotation_id);

-- =====================================================
-- 11. ARTICLES (from search-results.json and articles/)
-- =====================================================

CREATE TABLE article_searches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_date DATE NOT NULL REFERENCES daily_scans(scan_date) ON DELETE CASCADE,
    query_name VARCHAR(100) NOT NULL,  -- e.g., "Vietstock TA VHM"
    query_text TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'success',
    article_count INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_search_query UNIQUE (scan_date, query_name)
);

CREATE TABLE articles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    search_id UUID NOT NULL REFERENCES article_searches(id) ON DELETE CASCADE,

    title TEXT NOT NULL,
    url TEXT NOT NULL,
    domain VARCHAR(100),
    summary TEXT,
    summary_length INTEGER,
    search_description TEXT,
    file_path TEXT,  -- Legacy: local path to markdown file
    scraped_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_search_date ON article_searches(scan_date DESC);
CREATE INDEX idx_articles_search ON articles(search_id);
CREATE INDEX idx_articles_domain ON articles(domain);

-- =====================================================
-- 12. LEARNINGS
-- =====================================================

-- Summary statistics (singleton, updated daily)
CREATE TABLE learnings_summary (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    last_updated DATE NOT NULL,
    rolling_window_days INTEGER DEFAULT 7,
    total_days INTEGER,
    total_recs INTEGER,
    overall_entry_hit_rate DECIMAL(6, 2),
    overall_win_rate DECIMAL(6, 2),
    avg_pnl_percent DECIMAL(8, 4),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Winning/Losing patterns
CREATE TABLE learning_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern_type VARCHAR(10) NOT NULL CHECK (pattern_type IN ('winning', 'losing')),
    pattern_description TEXT NOT NULL,
    win_rate DECIMAL(6, 2),
    loss_rate DECIMAL(6, 2),
    sample_size INTEGER,
    actionable_rule TEXT,
    avoid_rule TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_patterns_type ON learning_patterns(pattern_type);

-- Sector insights
CREATE TABLE sector_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sector_id INTEGER NOT NULL REFERENCES sectors(id),
    bias sector_bias,
    win_rate DECIMAL(6, 2),

    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_sector_insight UNIQUE (sector_id)
);

-- Ticker insights
CREATE TABLE ticker_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker VARCHAR(10) NOT NULL UNIQUE,
    recent_accuracy DECIMAL(6, 2),

    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- 12b. DAILY RECORDS
-- =====================================================

CREATE TABLE daily_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_date DATE NOT NULL UNIQUE,
    market_regime market_regime,

    -- Day summary
    total_recs INTEGER,
    entry_hit_rate DECIMAL(6, 2),
    win_rate DECIMAL(6, 2),
    best_call TEXT,
    worst_call TEXT,
    key_insight TEXT,

    -- Mode compliance
    trading_mode trading_mode,
    mode_compliance BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_records_date ON daily_records(record_date DESC);

-- Mode violations per day
CREATE TABLE mode_violations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_id UUID NOT NULL REFERENCES daily_records(id) ON DELETE CASCADE,
    violation_text TEXT NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Daily recommendations
CREATE TABLE daily_recommendations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_id UUID NOT NULL REFERENCES daily_records(id) ON DELETE CASCADE,

    ticker VARCHAR(10) NOT NULL,
    action rec_action NOT NULL,
    entry_price_vnd BIGINT,
    stop_price_vnd BIGINT,
    target_price_vnd BIGINT,
    size_shares INTEGER,
    rationale TEXT,
    section VARCHAR(50),  -- e.g., "MY_HOLDINGS", "TOP_PICKS", "SKIP_THESE"

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rec_record ON daily_recommendations(record_id);
CREATE INDEX idx_rec_ticker ON daily_recommendations(ticker);
CREATE INDEX idx_rec_action ON daily_recommendations(action);

-- Daily evaluations
CREATE TABLE daily_evaluations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_id UUID NOT NULL REFERENCES daily_records(id) ON DELETE CASCADE,

    ticker VARCHAR(10) NOT NULL,
    recommendation rec_action NOT NULL,
    section TEXT,
    entry_hit BOOLEAN DEFAULT FALSE,
    stop_hit BOOLEAN DEFAULT FALSE,
    target_hit BOOLEAN DEFAULT FALSE,
    eod_price_vnd BIGINT,
    pnl_percent DECIMAL(8, 4),
    status eval_status,
    analysis TEXT,
    won BOOLEAN,
    strategy VARCHAR(20),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_eval_record ON daily_evaluations(record_id);
CREATE INDEX idx_eval_ticker ON daily_evaluations(ticker);
CREATE INDEX idx_eval_status ON daily_evaluations(status);

-- Midday data per day
CREATE TABLE midday_data (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_id UUID NOT NULL REFERENCES daily_records(id) ON DELETE CASCADE,

    trading_mode trading_mode,
    entries_hit INTEGER,
    afternoon_plan JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_midday_record UNIQUE (record_id)
);

-- Midday summary per day
CREATE TABLE midday_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_id UUID NOT NULL REFERENCES daily_records(id) ON DELETE CASCADE,

    adjustments_made INTEGER,
    adjustments_helpful INTEGER,
    adjustments_harmful INTEGER,
    afternoon_accuracy DECIMAL(6, 2),
    key_adjustment TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_midday_summary UNIQUE (record_id)
);

-- Rotation evaluation per day
CREATE TABLE rotation_evaluations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_id UUID NOT NULL REFERENCES daily_records(id) ON DELETE CASCADE,

    market_regime market_regime,
    hot_avg_return DECIMAL(8, 4),
    cold_avg_return DECIMAL(8, 4),
    market_avg_return DECIMAL(8, 4),
    hot_vs_market DECIMAL(8, 4),
    cold_vs_market DECIMAL(8, 4),
    hot_hit_rate DECIMAL(6, 2),
    cold_hit_rate DECIMAL(6, 2),
    overall_accuracy DECIMAL(6, 2),
    rotation_effective BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_rotation_eval UNIQUE (record_id)
);

-- Sector returns per day (normalized from rotation_evaluation.sector_returns)
CREATE TABLE rotation_sector_returns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rotation_eval_id UUID NOT NULL REFERENCES rotation_evaluations(id) ON DELETE CASCADE,
    sector_id INTEGER NOT NULL REFERENCES sectors(id),
    return_pct DECIMAL(8, 4),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Macro evaluation per day
CREATE TABLE macro_evaluations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_id UUID NOT NULL REFERENCES daily_records(id) ON DELETE CASCADE,

    global_risk_regime global_risk_regime,
    dxy_value DECIMAL(8, 3),
    vix_value DECIMAL(6, 2),
    vn_index_change_pct DECIMAL(8, 4),
    regime_appropriate BOOLEAN,
    foreign_flow_aligned BOOLEAN,
    recommendation_compliance BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_macro_eval UNIQUE (record_id)
);

-- =====================================================
-- 12c. AGGREGATED PATTERNS
-- =====================================================

-- Midday patterns aggregate (singleton)
CREATE TABLE midday_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    days_with_midday INTEGER,
    adjustment_win_rate DECIMAL(6, 2),
    when_helpful JSONB,  -- Array of strings
    when_harmful JSONB,  -- Array of strings
    average_improvement DECIMAL(8, 4),

    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trading mode patterns aggregate (singleton)
CREATE TABLE trading_mode_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mode_compliance_rate DECIMAL(6, 2),
    mode_violations JSONB,  -- Array of strings
    mode_appropriate_win_rate DECIMAL(6, 2),

    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Rotation patterns aggregate (singleton)
CREATE TABLE rotation_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    total_days INTEGER,
    overall_accuracy DECIMAL(6, 2),
    hot_hit_rate DECIMAL(6, 2),
    cold_hit_rate DECIMAL(6, 2),
    avg_hot_vs_market DECIMAL(8, 4),
    avg_cold_vs_market DECIMAL(8, 4),

    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Per-sector rotation scores
CREATE TABLE rotation_sector_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern_id UUID NOT NULL REFERENCES rotation_patterns(id) ON DELETE CASCADE,
    sector_id INTEGER NOT NULL REFERENCES sectors(id),
    as_hot_accuracy DECIMAL(6, 2),
    as_cold_accuracy DECIMAL(6, 2),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_rotation_sector UNIQUE (pattern_id, sector_id)
);

-- Macro patterns aggregate (singleton)
CREATE TABLE macro_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    total_days INTEGER,
    overall_accuracy DECIMAL(6, 2),
    false_alarms INTEGER,
    missed_drops INTEGER,

    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Per-regime macro accuracy
CREATE TABLE macro_regime_accuracy (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern_id UUID NOT NULL REFERENCES macro_patterns(id) ON DELETE CASCADE,
    regime global_risk_regime NOT NULL,
    days_count INTEGER,
    correct_count INTEGER,
    avg_vn_change DECIMAL(8, 4),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_macro_regime UNIQUE (pattern_id, regime)
);

-- =====================================================
-- MIDDAY CHECK TABLES (from midday-check.json)
-- =====================================================

CREATE TABLE midday_checks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_date DATE NOT NULL UNIQUE REFERENCES daily_scans(scan_date) ON DELETE CASCADE,
    trading_mode trading_mode NOT NULL,
    morning_reflection TEXT,
    afternoon_plan JSONB,
    capital_note TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Entries hit at midday
CREATE TABLE midday_entries_hit (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    midday_id UUID NOT NULL REFERENCES midday_checks(id) ON DELETE CASCADE,

    ticker VARCHAR(10) NOT NULL,
    recommended_entry_vnd BIGINT,
    actual_low_vnd BIGINT,
    current_price_vnd BIGINT,
    status TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Big movers at midday
CREATE TABLE midday_big_movers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    midday_id UUID NOT NULL REFERENCES midday_checks(id) ON DELETE CASCADE,

    ticker VARCHAR(10) NOT NULL,
    open_price_vnd BIGINT,
    current_price_vnd BIGINT,
    change_pct DECIMAL(8, 4),
    direction VARCHAR(10),  -- 'up' or 'down'

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Position alerts at midday
CREATE TABLE midday_position_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    midday_id UUID NOT NULL REFERENCES midday_checks(id) ON DELETE CASCADE,

    ticker VARCHAR(10) NOT NULL,
    current_price_vnd BIGINT,
    level_vnd BIGINT,
    level_type VARCHAR(20),  -- 'stop', 'target'
    distance_pct DECIMAL(8, 4),
    urgency TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_midday_date ON midday_checks(scan_date DESC);
CREATE INDEX idx_midday_entries ON midday_entries_hit(midday_id);
CREATE INDEX idx_midday_movers ON midday_big_movers(midday_id);
CREATE INDEX idx_midday_alerts ON midday_position_alerts(midday_id);

-- =====================================================
-- AUDIT & SYNC TRACKING
-- =====================================================

-- Track data imports/syncs
CREATE TABLE sync_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(50) NOT NULL,  -- 'notion', 'json', 'learnings'
    table_name VARCHAR(50) NOT NULL,
    sync_type VARCHAR(20) NOT NULL,  -- 'full', 'incremental'
    records_synced INTEGER,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running',
    error_message TEXT
);

CREATE INDEX idx_sync_log_source ON sync_log(source);
CREATE INDEX idx_sync_log_status ON sync_log(status);

-- =====================================================
-- VIEWS for common queries
-- =====================================================

-- Current portfolio with P/L
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

-- Latest technicals with levels
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

-- Trade performance by ticker
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

-- Swing watchlist with sector names
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

-- Long-term watchlist with sector names
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

-- =====================================================
-- FUNCTIONS for common operations
-- =====================================================

-- Calculate deployable cash
CREATE OR REPLACE FUNCTION get_deployable_cash()
RETURNS BIGINT AS $$
DECLARE
    total_cash BIGINT;
    min_reserve BIGINT := 10000000;  -- 10M VND
BEGIN
    SELECT COALESCE(SUM(shares * avg_cost_vnd), 0)
    INTO total_cash
    FROM portfolio_holdings
    WHERE holding_type = 'Cash';

    RETURN GREATEST(0, total_cash - min_reserve);
END;
$$ LANGUAGE plpgsql;

-- Get current trading mode
CREATE OR REPLACE FUNCTION get_trading_mode()
RETURNS trading_mode AS $$
DECLARE
    deployable BIGINT;
BEGIN
    deployable := get_deployable_cash();

    IF deployable > 5000000 THEN
        RETURN 'NORMAL';
    ELSIF deployable > 0 THEN
        RETURN 'LOW_CASH';
    ELSE
        RETURN 'REALLOCATION';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Get sector ID by name
CREATE OR REPLACE FUNCTION get_sector_id(sector_name VARCHAR)
RETURNS INTEGER AS $$
DECLARE
    sid INTEGER;
BEGIN
    SELECT id INTO sid FROM sectors WHERE name = LOWER(sector_name);
    RETURN sid;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply timestamp triggers
CREATE TRIGGER tr_portfolio_updated_at BEFORE UPDATE ON portfolio_holdings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_swing_updated_at BEFORE UPDATE ON swing_watchlist
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_longterm_updated_at BEFORE UPDATE ON longterm_watchlist
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_goals_updated_at BEFORE UPDATE ON goals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_stocks_updated_at BEFORE UPDATE ON stocks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_learnings_summary_updated_at BEFORE UPDATE ON learnings_summary
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =====================================================
-- END OF SCHEMA
-- =====================================================
