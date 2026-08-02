-- 322_catalysts_factors_column.sql
-- Fix 2 of the narrative+catalyst systemic plan (2026-04-21).
-- Add `catalyst_factors TEXT[]` to the catalysts table. Replaces the
-- hardcoded `_SHOCK_TO_FACTORS` dict in pipeline/context_blocks_macro.py
-- that mapped one catalyst_key to `["oil_price","usd_vnd"]` — future
-- geopolitical shocks (Red Sea, Taiwan, sanctions) now add a row + factor
-- list with no code deploy.
--
-- Allowed factor values match the geo-exposure scoring keys used by
-- shared/rules/catalyst_override.classify_geo_label:
--   oil_price | usd_vnd | dxy | vix | rates | global_risk
--
-- The constraint is a CHECK on the unnested array so any bad value fails
-- at write time with a loud error (fail-loud per CLAUDE.md).

BEGIN;

ALTER TABLE catalysts
  ADD COLUMN IF NOT EXISTS catalyst_factors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

-- Validation: every element must be one of the 6 allowed keys.
ALTER TABLE catalysts
  DROP CONSTRAINT IF EXISTS catalysts_factors_allowed;

ALTER TABLE catalysts
  ADD CONSTRAINT catalysts_factors_allowed
  CHECK (
    catalyst_factors <@ ARRAY[
      'oil_price',
      'usd_vnd',
      'dxy',
      'vix',
      'rates',
      'global_risk'
    ]::TEXT[]
  );

-- Backfill: the only geopolitical catalyst currently active with a
-- meaningful factor set.
UPDATE catalysts
SET catalyst_factors = ARRAY['oil_price','usd_vnd']::TEXT[],
    updated_at = NOW()
WHERE catalyst_key = 'hormuz_closure_2026'
  AND catalyst_factors = ARRAY[]::TEXT[];

-- Audit.
SELECT catalyst_key, catalyst_type, catalyst_factors
FROM catalysts
WHERE catalyst_factors <> ARRAY[]::TEXT[]
ORDER BY catalyst_key;

COMMIT;
