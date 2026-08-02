-- Migration 128: Widen fiscal_quarter column in earnings_calendar to VARCHAR(15)
-- "Annual-2026" is 11 chars, exceeds original VARCHAR(10) limit

ALTER TABLE earnings_calendar
ALTER COLUMN fiscal_quarter TYPE VARCHAR(15);
