-- 328_drop_screen_bank_max_de.sql
-- Cleanup paired with migration 327.
--
-- `screen_bank_max_de` (trading_config) is the legacy companion of the
-- hardcoded BANK_TICKERS frozenset in scripts/agents/screening.py. Both
-- are replaced by the banking row in `sector_screening_overrides` (max_de
-- = 12.0). Migration 327 wrote the override and 327's companion code
-- removed the frozenset; this migration drops the now-dead column so
-- there is exactly one source of truth for bank D/E.
--
-- Safe because no Python code still reads the column (grep-verified).

BEGIN;

ALTER TABLE trading_config
    DROP COLUMN IF EXISTS screen_bank_max_de;

COMMIT;
