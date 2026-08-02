-- Backfill sector_id from stocks table (all 25 rows were NULL from batch insert)
UPDATE company_profiles
SET sector_id = s.sector_id
FROM stocks s
WHERE company_profiles.ticker = s.ticker
  AND company_profiles.sector_id IS NULL;

-- Reset bank export_splits to domestic-only
-- International banking ops (branches, trade finance, remittances) != goods exports
-- Misleads agents evaluating usd_vnd sensitivity via export_split
UPDATE company_profiles
SET export_split = '{"domestic_pct": 100, "exports": []}'::jsonb
WHERE ticker IN ('SHB', 'VCB', 'VPB', 'TPB', 'MBB');
