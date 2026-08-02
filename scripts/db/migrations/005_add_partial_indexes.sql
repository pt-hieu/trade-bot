-- Migration: 005_add_partial_indexes.sql
-- Description: Add partial indexes for queries that always filter on specific conditions
-- Impact: MEDIUM - Smaller indexes, faster queries for common filters

-- Swing watchlist queries always filter is_active = TRUE
CREATE INDEX IF NOT EXISTS idx_swing_watchlist_active
    ON swing_watchlist(sector_id, ticker) WHERE is_active = TRUE;

-- Long-term watchlist queries always filter is_active = TRUE
CREATE INDEX IF NOT EXISTS idx_longterm_watchlist_active
    ON longterm_watchlist(sector_id, ticker) WHERE is_active = TRUE;

-- Goal queries always filter status = 'Active'
CREATE INDEX IF NOT EXISTS idx_goals_active
    ON goals(deadline) WHERE status = 'Active';

-- Trade queries filter action = 'BUY' in get_recent_trades()
CREATE INDEX IF NOT EXISTS idx_trade_entries_buy
    ON trade_entries(trade_date DESC, ticker) WHERE action = 'BUY';

-- Portfolio holdings exclude Cash type in most queries
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_stocks
    ON portfolio_holdings(ticker) WHERE holding_type != 'Cash';
