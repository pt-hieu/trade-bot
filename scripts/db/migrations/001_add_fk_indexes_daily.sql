-- Migration: 001_add_fk_indexes_daily.sql
-- Description: Add missing FK indexes on daily scan child tables
-- Impact: CRITICAL - These tables are queried by get_all_technicals(), get_ticker_technicals()
-- Note: Using CREATE INDEX (not CONCURRENTLY) for local Docker compatibility

-- daily_prices: FK to daily_scans(scan_date)
CREATE INDEX IF NOT EXISTS idx_daily_prices_scan_date
    ON daily_prices(scan_date);

-- daily_technicals: FK to daily_scans(scan_date)
CREATE INDEX IF NOT EXISTS idx_daily_technicals_scan_date
    ON daily_technicals(scan_date);

-- daily_levels: FK to daily_scans(scan_date)
CREATE INDEX IF NOT EXISTS idx_daily_levels_scan_date
    ON daily_levels(scan_date);

-- macro_events: FK to daily_scans(scan_date)
CREATE INDEX IF NOT EXISTS idx_macro_events_scan_date
    ON macro_events(scan_date);
