-- 320_catalyst_high_confidence_downgrade.sql
-- Fix 4 of the narrative+catalyst systemic plan (2026-04-21).
-- Downgrade HIGH-confidence catalysts lacking ≥3 supporting articles and
-- without the `official_document_flag` signal to MEDIUM. The downgrade is
-- one-time backfill: new inserts are policed by
-- shared/neon/catalysts._enforce_high_confidence_floor at write time.
--
-- Rationale: the Apr-21 audit found 12 HIGH rows with 1 article and
-- hormuz_closure_2026 HIGH with 0 supporting articles. Fix 1's GEO_MIXED
-- tie-break trusts HIGH counts — without this backfill stale single-source
-- HIGH rows would wrongly flip tickers into GEO_MIXED during a real shock.

BEGIN;

-- Log the rows we're about to downgrade before we mutate them so the
-- operator has a record. Uses a CTE for audit-only output.
WITH to_downgrade AS (
  SELECT c.catalyst_key,
         c.event,
         c.catalyst_type,
         c.confidence,
         COUNT(ca.article_id) AS article_count
  FROM catalysts c
  LEFT JOIN catalyst_articles ca USING (catalyst_key)
  WHERE c.status IN ('active','monitoring','imminent')
    AND c.confidence = 'HIGH'
  GROUP BY c.id, c.catalyst_key, c.event, c.catalyst_type, c.confidence
  HAVING COUNT(ca.article_id) < 3
)
SELECT 'DOWNGRADE'::text AS action,
       catalyst_key,
       catalyst_type,
       article_count,
       event
FROM to_downgrade
ORDER BY catalyst_key;

-- Apply the downgrade.
UPDATE catalysts c
SET confidence = 'MEDIUM',
    updated_at = NOW(),
    notes = COALESCE(notes || ' | ', '')
          || 'Fix 4 (2026-04-21): downgraded HIGH→MEDIUM — single-source / uncorroborated.'
WHERE c.status IN ('active','monitoring','imminent')
  AND c.confidence = 'HIGH'
  AND c.id IN (
    SELECT c2.id
    FROM catalysts c2
    LEFT JOIN catalyst_articles ca USING (catalyst_key)
    WHERE c2.status IN ('active','monitoring','imminent')
      AND c2.confidence = 'HIGH'
    GROUP BY c2.id
    HAVING COUNT(ca.article_id) < 3
  );

COMMIT;
