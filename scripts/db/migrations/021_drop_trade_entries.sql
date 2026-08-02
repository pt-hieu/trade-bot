-- Drop legacy trade_entries table.
-- All trade data now lives in trades_calculated (web app source of truth).
-- Agent tools have been updated to read from trades_calculated.

DROP TABLE IF EXISTS trade_entries CASCADE;
