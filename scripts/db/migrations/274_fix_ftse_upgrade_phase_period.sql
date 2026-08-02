-- Fix malformed phase period in ftse_upgrade catalyst
-- "Sep 21+, 2026" → "Sep 21, 2026+" (plus must be after year, not after day)
-- This was causing parse_phase_period() to return None, making the effective phase invisible

UPDATE catalysts
SET phases = jsonb_set(
    phases,
    '{effective,period}',
    '"Sep 21, 2026+"'
),
    updated_at = NOW()
WHERE catalyst_key = 'ftse_upgrade'
  AND phases->'effective'->>'period' = 'Sep 21+, 2026';
