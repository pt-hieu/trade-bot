-- 321_reclassify_existing_catalysts.sql
-- Fix 3 backfill (2026-04-21): reclassify the 14+ existing mis-typed active
-- catalysts discovered in the Apr-21 audit. The classifier
-- (shared/rules/catalyst_classifier) runs on all NEW discoveries going
-- forward; this migration one-shots the existing rows.
--
-- Mapping derived from the same rule set as
-- shared/rules/catalyst_classifier.py:
--   macro         ← Fed / FOMC / IMF / central-bankers statements
--   geopolitical  ← Hormuz / force-majeure / Middle East crisis / Russia oil
--   commodity     ← pure oil data with no geopolitical trigger
--   regulatory    ← VN government actors (unchanged)

BEGIN;

-- Macro: Fed / IMF / central-bank policy statements
UPDATE catalysts
SET catalyst_type = 'macro', updated_at = NOW()
WHERE catalyst_key IN (
  'cleveland_fed_president_hammac',
  'fed_beige_book_reports_us_busi',
  'fed_governor_waller_states_ira',
  'global_central_bankers_survey_',
  'imf_cut_global_gdp_outlook_to_',
  'new_york_fed_president_william',
  'trump_threatened_to_fire_fed_c',
  'state_bank_deputy_governor_war'
)
  AND catalyst_type = 'regulatory'
  AND status IN ('active','monitoring','imminent');

-- Geopolitical: Hormuz / Middle East crisis / force-majeure / Russia sanctions
-- Note: these rows don't have `phases` populated — lifecycle will age them out
-- normally. New geopolitical discoveries going forward MUST supply phases.
UPDATE catalysts
SET catalyst_type = 'geopolitical', updated_at = NOW()
WHERE catalyst_key IN (
  'conventional_marine_fuel_becom',
  'corporate_bond_market_slowdown',
  'kuwait_declares_force_majeure_',
  'ships_plying_strait_of_hormuz_',
  'us_will_not_extend_policy_exem',
  'japan_pledged_$10_billion_fina',
  'us_oil_exports_hit_record_high'
)
  AND catalyst_type = 'regulatory'
  AND status IN ('active','monitoring','imminent');

-- Audit summary
SELECT catalyst_type, COUNT(*) AS row_count
FROM catalysts
WHERE status IN ('active','monitoring','imminent')
GROUP BY catalyst_type
ORDER BY row_count DESC;

COMMIT;
