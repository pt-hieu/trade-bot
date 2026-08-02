-- SWI-322: Universe layer expansion — admit brand-new rally tickers in Phase 0.
--
-- Diagnosis (2026-05-11): morning scan ran on only 35 tickers; missed rally winners
-- DCM +6.72%, SAB +2.92%, DPM +2.13%, DXG +1.62%. Spearman(score, fwd_1d) = -0.49.
-- Root cause: the universe, not the scorer. 9 tickers absent from swing_watchlist;
-- 5 also absent from the stocks table. DXG/FRT misclassified as banking.
--
-- This migration inverts the SWI-304 "never widen the tradable set" invariant for
-- Phase 0 rally_readmit ONLY. Catalyst revision retains the invariant.

BEGIN;

-- ── Pre-flight: fail loudly if required sectors are absent ──────────────────
DO $$
DECLARE
    missing_count INT;
BEGIN
    SELECT COUNT(*) INTO missing_count FROM (VALUES
        ('industrial'), ('real_estate'), ('consumer'), ('state_owned')
    ) AS v(name) WHERE NOT EXISTS (SELECT 1 FROM sectors s WHERE s.name = v.name);
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'migration 345: required sectors missing — % rows not found', missing_count;
    END IF;
END $$;

-- ── 1. Backfill missing stocks rows ──────────────────────────────────────────
INSERT INTO stocks (ticker, sector_id, stock_type)
SELECT v.ticker, (SELECT id FROM sectors WHERE name = v.sector_slug), 'Private'
FROM (VALUES
    ('REE', 'industrial'),   -- mech/electrical conglomerate
    ('HSG', 'industrial'),   -- steel
    ('NKG', 'industrial'),   -- steel
    ('NT2', 'state_owned'),  -- PV Power gen (EVN subsidiary); no utilities sector exists
    ('VEA', 'industrial')    -- auto/industrial
) AS v(ticker, sector_slug)
ON CONFLICT (ticker) DO NOTHING;

-- ── 2. Fix DXG and FRT classifications in stocks ─────────────────────────────
UPDATE stocks
SET sector_id = (SELECT id FROM sectors WHERE name = 'real_estate'),
    updated_at = NOW()
WHERE ticker = 'DXG'
  AND sector_id IS DISTINCT FROM (SELECT id FROM sectors WHERE name = 'real_estate');

UPDATE stocks
SET sector_id = (SELECT id FROM sectors WHERE name = 'consumer'),
    updated_at = NOW()
WHERE ticker = 'FRT'
  AND sector_id IS DISTINCT FROM (SELECT id FROM sectors WHERE name = 'consumer');

-- ── 3. Mirror DXG/FRT corrections on swing_watchlist (only if row exists) ────
UPDATE swing_watchlist
SET sector_id = (SELECT id FROM sectors WHERE name = 'real_estate'),
    updated_at = NOW()
WHERE ticker = 'DXG'
  AND sector_id IS DISTINCT FROM (SELECT id FROM sectors WHERE name = 'real_estate');

UPDATE swing_watchlist
SET sector_id = (SELECT id FROM sectors WHERE name = 'consumer'),
    updated_at = NOW()
WHERE ticker = 'FRT'
  AND sector_id IS DISTINCT FROM (SELECT id FROM sectors WHERE name = 'consumer');

-- ── 4. Seed swing_watchlist with the 9 missing tickers (unpinned, audit trail) ─
-- pin_reason='SWI-322 universe-seed 2026-05-11' is a forensic marker; is_pinned=FALSE
-- means the weekly LLM pruner can still remove them. The string enables queries:
--   SELECT ticker, is_active FROM swing_watchlist
--   WHERE pin_reason = 'SWI-322 universe-seed 2026-05-11';
INSERT INTO swing_watchlist (ticker, sector_id, stock_type, is_active, is_pinned, pin_reason)
SELECT v.ticker, st.sector_id, 'Private', TRUE, FALSE, 'SWI-322 universe-seed 2026-05-11'
FROM (VALUES ('DCM'), ('DPM'), ('DGC'), ('HSG'), ('NKG'),
             ('REE'), ('NT2'), ('VEA'), ('FRT')) AS v(ticker)
JOIN stocks st ON st.ticker = v.ticker
ON CONFLICT (ticker) DO UPDATE
    SET is_active = TRUE,
        sector_id = EXCLUDED.sector_id,
        pin_reason = COALESCE(swing_watchlist.pin_reason, EXCLUDED.pin_reason),
        updated_at = NOW();

-- ── 5. trading_config knobs for the new-ticker admission path ────────────────
ALTER TABLE trading_config
    ADD COLUMN IF NOT EXISTS rally_readmit_new_ticker_ret_5d_min    NUMERIC(5,4) NOT NULL DEFAULT 0.08,
    ADD COLUMN IF NOT EXISTS rally_readmit_new_ticker_vol_ratio_min NUMERIC(5,2) NOT NULL DEFAULT 2.0;

COMMENT ON COLUMN trading_config.rally_readmit_new_ticker_ret_5d_min IS
    'SWI-322: min 5-day return required to admit a ticker NOT currently in swing_watchlist. '
    'Stricter than rally_readmit_ret_5d_min because new tickers lack curation.';
COMMENT ON COLUMN trading_config.rally_readmit_new_ticker_vol_ratio_min IS
    'SWI-322: min 20-day volume ratio required to admit a brand-new ticker.';

INSERT INTO schema_migrations (version)
VALUES ('345_universe_layer_expansion')
ON CONFLICT DO NOTHING;

COMMIT;
