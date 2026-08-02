-- Add unique constraint on (ticker, price_date) to prevent duplicate price rows.
-- The existing UNIQUE(scan_date, ticker) allows different scan_dates to insert
-- the same ticker+price_date. This migration deduplicates and prevents that.
--
-- NOTE: This changes the insert behavior. insert_daily_prices must be updated
-- to use ON CONFLICT (ticker, price_date) instead of ON CONFLICT (scan_date, ticker).

-- Step 1: Remove duplicates, keeping the most recent scan_date per (ticker, price_date)
DELETE FROM daily_prices dp
WHERE dp.id NOT IN (
    SELECT DISTINCT ON (ticker, price_date) id
    FROM daily_prices
    ORDER BY ticker, price_date, scan_date DESC
);

-- Step 2: Drop old constraint and add new one
ALTER TABLE daily_prices DROP CONSTRAINT IF EXISTS uq_price_scan_ticker;

ALTER TABLE daily_prices
ADD CONSTRAINT uq_daily_prices_ticker_price_date UNIQUE (ticker, price_date);
