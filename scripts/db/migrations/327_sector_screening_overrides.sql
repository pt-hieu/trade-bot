-- 327_sector_screening_overrides.sql
-- L5 of the 2026-04-24 regime+screen systemic fix.
--
-- Move fundamental-screen thresholds from hardcoded BANK_TICKERS frozenset +
-- flat trading_config defaults → sector-aware overrides joined via
-- stocks.sector_id. Adds two missing sector buckets (broker_dealer,
-- industrial), introduces a sector_screening_overrides table, bootstraps
-- per-sector threshold rows, and assigns sector_id on tickers that today
-- live under the BANK_TICKERS hardcode or need the new buckets (HCM/SSI
-- brokers, GVR rubber/industrial). Also adds two tolerance knobs on
-- trading_config used by the new composite scorer in screening.py.
--
-- Rationale: 2026-04-23 brief rejected GVR/VHM/HCM on sub-20% threshold
-- misses. Real-estate D/E >2 is normal; broker ROE dynamics differ; GVR
-- rubber sits at PE 24.6 which is inside the industrial norm but outside
-- the flat 20.0 cap. Single threshold table cannot express that.

BEGIN;

-- ---------------------------------------------------------------------
-- Part 1. Seed missing sectors.
-- ---------------------------------------------------------------------
INSERT INTO sectors (name, display_name) VALUES
    ('broker_dealer', 'Broker / Dealer'),
    ('industrial',    'Industrial')
ON CONFLICT (name) DO NOTHING;

-- ---------------------------------------------------------------------
-- Part 2. Create sector_screening_overrides.
-- ---------------------------------------------------------------------
-- Any column NULL means "inherit trading_config default for this metric".
-- Composite scoring in screening.py treats a sector override as the
-- threshold and falls back to trading_config.screen_* otherwise. This
-- keeps the write path sparse and avoids duplicating unchanged values.
CREATE TABLE IF NOT EXISTS sector_screening_overrides (
    sector_id        INTEGER PRIMARY KEY REFERENCES sectors(id),
    max_pe           NUMERIC(6, 2),
    max_pb           NUMERIC(5, 2),
    min_roe_pct      NUMERIC(5, 2),
    min_margin_pct   NUMERIC(5, 2),
    max_de           NUMERIC(5, 2),
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------
-- Part 3. Bootstrap per-sector overrides.
-- ---------------------------------------------------------------------
-- banking: migrates the existing BANK_TICKERS-hardcoded D/E=12.0 special
--          case. Other thresholds inherit defaults.
-- real_estate: VHM/VRE/NVL routinely run D/E >2 and PB >2.5 — flat 2.0/2.5
--              caps are wrong for the sector. Relax to 3.0/3.0.
-- broker_dealer: HCM/SSI ROE dynamics — earnings are cyclical, 8% floor
--                is the long-run norm for VN brokers.
-- industrial: GVR rubber / industrial equipment trade at higher P/E than
--             consumer staples. 25.0 cap is the sector norm.
INSERT INTO sector_screening_overrides
    (sector_id, max_pe, max_pb, min_roe_pct, min_margin_pct, max_de, notes)
SELECT id, NULL, NULL, NULL, NULL, 12.00, 'Banks inherit prior BANK_TICKERS special-case D/E cap.'
FROM sectors WHERE name = 'banking'
ON CONFLICT (sector_id) DO NOTHING;

INSERT INTO sector_screening_overrides
    (sector_id, max_pe, max_pb, min_roe_pct, min_margin_pct, max_de, notes)
SELECT id, NULL, 3.00, NULL, NULL, 3.00, 'Real estate — VN developers normally leveraged; PB tracks land bank markups.'
FROM sectors WHERE name = 'real_estate'
ON CONFLICT (sector_id) DO NOTHING;

INSERT INTO sector_screening_overrides
    (sector_id, max_pe, max_pb, min_roe_pct, min_margin_pct, max_de, notes)
SELECT id, NULL, NULL, 8.00, NULL, 3.00, 'Brokers — ROE cyclical (8% long-run floor); VN brokers run margin books so D/E up to 3.0 is normal.'
FROM sectors WHERE name = 'broker_dealer'
ON CONFLICT (sector_id) DO NOTHING;

INSERT INTO sector_screening_overrides
    (sector_id, max_pe, max_pb, min_roe_pct, min_margin_pct, max_de, notes)
SELECT id, 25.00, NULL, NULL, NULL, NULL, 'Industrial/commodity — GVR-type equities trade above the consumer P/E cap.'
FROM sectors WHERE name = 'industrial'
ON CONFLICT (sector_id) DO NOTHING;

-- ---------------------------------------------------------------------
-- Part 4. Assign sector_id for tickers that need it.
-- ---------------------------------------------------------------------
-- Banks: everyone currently in the BANK_TICKERS frozenset. We upsert the
--        (ticker, sector_id) pair so existing rows flip and missing rows
--        (e.g. UPCoM tickers still absent from stocks) do nothing.
UPDATE stocks
SET sector_id  = (SELECT id FROM sectors WHERE name = 'banking'),
    updated_at = NOW()
WHERE ticker IN (
    'TCB','VCB','BID','ACB','MBB','VPB','HDB','STB','CTG','TPB',
    'SHB','VIB','OCB','KLB','SSB','LPB','MSB','EIB','ABB','NAB'
);

-- Brokers
UPDATE stocks
SET sector_id  = (SELECT id FROM sectors WHERE name = 'broker_dealer'),
    updated_at = NOW()
WHERE ticker IN ('HCM','SSI','VND','VCI','SHS','MBS');

-- Industrial / commodity (GVR rubber, BMP plastics, HT1 cement, DPM urea)
UPDATE stocks
SET sector_id  = (SELECT id FROM sectors WHERE name = 'industrial'),
    updated_at = NOW()
WHERE ticker IN ('GVR','BMP','HT1','DPM','DGC','DCM');

-- ---------------------------------------------------------------------
-- Part 5. Tolerance + composite knobs on trading_config.
-- ---------------------------------------------------------------------
-- screen_tolerance_pct: per-metric soft-fail band (default ±10%).
-- screen_composite_limit: sum-of-per-metric-scores cap before rejection
--   (0=pass, 1=soft, 2=hard — so default 1.0 allows one soft miss).
ALTER TABLE trading_config
    ADD COLUMN IF NOT EXISTS screen_tolerance_pct   NUMERIC(4, 3) DEFAULT 0.10,
    ADD COLUMN IF NOT EXISTS screen_composite_limit NUMERIC(4, 2) DEFAULT 1.00;

-- Backfill the single config row if it already exists so runtime readers
-- see the new defaults immediately.
UPDATE trading_config
SET screen_tolerance_pct   = COALESCE(screen_tolerance_pct,   0.10),
    screen_composite_limit = COALESCE(screen_composite_limit, 1.00);

COMMIT;
