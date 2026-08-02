-- Migration 330: Reclassify geopolitical shocks that were mis-tagged as
-- macro / regulatory by earlier classifier versions.
--
-- Context: AUDIT-2026-04-24-001 / ISSUE-2026-04-24-004. The classifier's
-- regex set rebuilt from GEOPOLITICAL_KEYWORDS missed morphology variants
-- (Iran/Iranian, Russia/Russian, QatarEnergy) and multi-word phrases
-- (Jones Act, stockpile drawdown). Iran-proxy catalysts were getting
-- filed as `macro` / `regulatory` instead of `geopolitical` with
-- phases required — which let them skip the phase-aware regime floor
-- and the geopolitical fan-out path.
--
-- This migration flips catalyst_type to `geopolitical` for every active
-- row that matches the expanded keyword set. Phases are seeded with a
-- conservative default (sustained_pressure) where the row lacks them;
-- the next catalyst-discovery run will refine via CatalystUpdate.

BEGIN;

-- Conservative default phase — sustained_pressure is a middle-severity
-- bucket that triggers the geopolitical fan-out without overstating
-- severity. Downstream discovery will update to immediate_shock or
-- resolution_or_escalation as evidence lands.
WITH to_fix AS (
    SELECT catalyst_key
    FROM catalysts
    WHERE status = 'active'
      AND catalyst_type IN ('macro', 'regulatory', 'commodity')
      AND (
          event ~* 'iran(ian)?'
          OR event ~* 'russia(n)?\s+oil'
          OR event ~* 'qatar(energy|i)?'
          OR event ~* 'kuwait(i)?'
          OR event ~* 'jones\s+act'
          OR event ~* 'stockpile\s+drawdown'
          OR event ~* 'gulf\s+blockade'
          OR event ~* 'marine\s+fuel'
          OR event ~* '(?:strait\s+of\s+)?hormuz'
          OR event ~* 'houthi'
          OR event ~* 'bab[- ]?el[- ]?mandeb'
          OR event ~* 'taiwan(ese)?'
          OR event ~* 'ukrain(e|ian)'
      )
)
UPDATE catalysts
SET catalyst_type = 'geopolitical',
    phases = COALESCE(
        phases,
        jsonb_build_object(
            'sustained_pressure', jsonb_build_object(
                'period', 'ongoing',
                'impact', 'NEGATIVE',
                'behavior', 'Seeded by migration 330 — awaiting refinement from next discovery run.'
            )
        )
    )
WHERE catalyst_key IN (SELECT catalyst_key FROM to_fix);

COMMIT;
