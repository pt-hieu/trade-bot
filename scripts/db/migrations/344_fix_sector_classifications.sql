-- SWI-304: Fix VIC/VRE/SAB sector_id rows + add rally_readmit thresholds.
--
-- Background: VIC and VRE were classified under "Consumer" in stocks/swing_watchlist
-- rows, while their natural peer cohort is "Real Estate". The weekly LLM rotation
-- scored VIC against the wrong peer group and silently deactivated it on 2026-04-25.
-- During the 5/4–5/8 rally (+6.6%), VIC therefore never reached pre_gate_candidates.
--
-- This migration also adds three columns to trading_config that drive the new
-- Phase 0 rally_readmit pre-pass (idempotent; defaults preserve current behavior
-- when nothing has rallied).

BEGIN;

-- ── Sector reclassification ──────────────────────────────────────────────────
WITH sector_ids AS (
    SELECT
        (SELECT id FROM sectors WHERE name = 'real_estate') AS real_estate_id,
        (SELECT id FROM sectors WHERE name = 'consumer')    AS consumer_id
)
UPDATE stocks
SET sector_id = sector_ids.real_estate_id, updated_at = NOW()
FROM sector_ids
WHERE ticker IN ('VIC', 'VRE')
  AND sector_id IS DISTINCT FROM sector_ids.real_estate_id
  AND sector_ids.real_estate_id IS NOT NULL;

UPDATE stocks
SET sector_id = (SELECT id FROM sectors WHERE name = 'consumer'), updated_at = NOW()
WHERE ticker = 'SAB'
  AND sector_id IS DISTINCT FROM (SELECT id FROM sectors WHERE name = 'consumer');

-- Mirror the change on swing_watchlist + longterm_watchlist rows so the active
-- pipeline reads the same sector even before the next weekly rebuild.
WITH sector_ids AS (
    SELECT
        (SELECT id FROM sectors WHERE name = 'real_estate') AS real_estate_id,
        (SELECT id FROM sectors WHERE name = 'consumer')    AS consumer_id
)
UPDATE swing_watchlist sw
SET sector_id = sector_ids.real_estate_id, updated_at = NOW()
FROM sector_ids
WHERE sw.ticker IN ('VIC', 'VRE')
  AND sw.sector_id IS DISTINCT FROM sector_ids.real_estate_id
  AND sector_ids.real_estate_id IS NOT NULL;

UPDATE swing_watchlist
SET sector_id = (SELECT id FROM sectors WHERE name = 'consumer'), updated_at = NOW()
WHERE ticker = 'SAB'
  AND sector_id IS DISTINCT FROM (SELECT id FROM sectors WHERE name = 'consumer');

UPDATE longterm_watchlist lw
SET sector_id = (SELECT id FROM sectors WHERE name = 'real_estate'), updated_at = NOW()
WHERE lw.ticker IN ('VIC', 'VRE')
  AND lw.sector_id IS DISTINCT FROM (SELECT id FROM sectors WHERE name = 'real_estate');

-- ── Rally-readmit configuration columns ──────────────────────────────────────
ALTER TABLE trading_config
    ADD COLUMN IF NOT EXISTS rally_readmit_ret_5d_min   NUMERIC(5,4) NOT NULL DEFAULT 0.05,
    ADD COLUMN IF NOT EXISTS rally_readmit_vol_ratio_min NUMERIC(5,2) NOT NULL DEFAULT 1.5,
    ADD COLUMN IF NOT EXISTS rally_readmit_daily_cap     INTEGER       NOT NULL DEFAULT 5;

COMMENT ON COLUMN trading_config.rally_readmit_ret_5d_min IS
    'SWI-304: minimum 5-trading-day return required for rally-volume readmit';
COMMENT ON COLUMN trading_config.rally_readmit_vol_ratio_min IS
    'SWI-304: minimum 20-day volume ratio required for rally-volume readmit';
COMMENT ON COLUMN trading_config.rally_readmit_daily_cap IS
    'SWI-304: maximum tickers re-admitted per day by Phase 0 rally pass';

-- Reactivate VIC + VRE so the next morning scan picks them up immediately.
-- The Python guard that landed alongside this migration prevents same-day
-- re-removal during a rally.
UPDATE swing_watchlist
SET is_active = TRUE, updated_at = NOW()
WHERE ticker IN ('VIC', 'VRE')
  AND is_active = FALSE
  AND (is_pinned = FALSE OR is_pinned IS NULL);

INSERT INTO schema_migrations (version)
VALUES ('344_fix_sector_classifications')
ON CONFLICT DO NOTHING;

COMMIT;
