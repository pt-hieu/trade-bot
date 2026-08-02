-- Migration 307: backfill double-encoded JSONB values caused by pattern-B bugs
-- in `scripts/shared/neon/*.py`. Every fix site listed below was shipping
-- `json.dumps(dict)` into a JSONB parameter WITHOUT an explicit ``::jsonb``
-- cast. asyncpg's registered jsonb codec then called ``json.dumps`` again on
-- the already-serialized string, wrapping it in quote characters so the
-- column ended up with ``jsonb_typeof = 'string'`` instead of
-- ``'object'``/``'array'``.
--
-- This migration unwraps those rows in place. It is idempotent — re-running
-- has no effect once a row's type is correct.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. macro_metrics.geopolitical_shock (RC2 entry point)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
    val JSONB;
    iterations INT;
BEGIN
    FOR r IN
        SELECT scan_date, geopolitical_shock
        FROM macro_metrics
        WHERE jsonb_typeof(geopolitical_shock) = 'string'
    LOOP
        val := r.geopolitical_shock;
        iterations := 0;
        WHILE jsonb_typeof(val) = 'string' AND iterations < 5 LOOP
            val := (val #>> '{}')::jsonb;
            iterations := iterations + 1;
        END LOOP;
        IF jsonb_typeof(val) = 'object' THEN
            UPDATE macro_metrics
            SET geopolitical_shock = val
            WHERE scan_date = r.scan_date;
        ELSE
            RAISE WARNING
                'macro_metrics.geopolitical_shock [%] still % after % unwraps',
                r.scan_date, jsonb_typeof(val), iterations;
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 2. alerts.alert_metadata
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
    val JSONB;
    iterations INT;
BEGIN
    FOR r IN
        SELECT id, alert_metadata
        FROM alerts
        WHERE jsonb_typeof(alert_metadata) = 'string'
    LOOP
        val := r.alert_metadata;
        iterations := 0;
        WHILE jsonb_typeof(val) = 'string' AND iterations < 5 LOOP
            val := (val #>> '{}')::jsonb;
            iterations := iterations + 1;
        END LOOP;
        IF jsonb_typeof(val) IN ('object', 'array') THEN
            UPDATE alerts SET alert_metadata = val WHERE id = r.id;
        ELSE
            RAISE WARNING
                'alerts.alert_metadata [%] still % after % unwraps',
                r.id, jsonb_typeof(val), iterations;
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 3. alert_conditions.params
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
    val JSONB;
    iterations INT;
BEGIN
    FOR r IN
        SELECT id, params
        FROM alert_conditions
        WHERE jsonb_typeof(params) = 'string'
    LOOP
        val := r.params;
        iterations := 0;
        WHILE jsonb_typeof(val) = 'string' AND iterations < 5 LOOP
            val := (val #>> '{}')::jsonb;
            iterations := iterations + 1;
        END LOOP;
        IF jsonb_typeof(val) IN ('object', 'array') THEN
            UPDATE alert_conditions SET params = val WHERE id = r.id;
        ELSE
            RAISE WARNING
                'alert_conditions.params [%] still % after % unwraps',
                r.id, jsonb_typeof(val), iterations;
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 4. morning_position_alerts.dissenting_views
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
    val JSONB;
    iterations INT;
BEGIN
    FOR r IN
        SELECT scan_date, ticker, dissenting_views
        FROM morning_position_alerts
        WHERE jsonb_typeof(dissenting_views) = 'string'
    LOOP
        val := r.dissenting_views;
        iterations := 0;
        WHILE jsonb_typeof(val) = 'string' AND iterations < 5 LOOP
            val := (val #>> '{}')::jsonb;
            iterations := iterations + 1;
        END LOOP;
        IF jsonb_typeof(val) IN ('array', 'object') THEN
            UPDATE morning_position_alerts
            SET dissenting_views = val
            WHERE scan_date = r.scan_date AND ticker = r.ticker;
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 5. rotation_evaluations.hot_sectors + cold_sectors
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
    val JSONB;
    iterations INT;
BEGIN
    FOR r IN
        SELECT id, hot_sectors
        FROM rotation_evaluations
        WHERE jsonb_typeof(hot_sectors) = 'string'
    LOOP
        val := r.hot_sectors;
        iterations := 0;
        WHILE jsonb_typeof(val) = 'string' AND iterations < 5 LOOP
            val := (val #>> '{}')::jsonb;
            iterations := iterations + 1;
        END LOOP;
        IF jsonb_typeof(val) IN ('array', 'object') THEN
            UPDATE rotation_evaluations SET hot_sectors = val WHERE id = r.id;
        END IF;
    END LOOP;

    FOR r IN
        SELECT id, cold_sectors
        FROM rotation_evaluations
        WHERE jsonb_typeof(cold_sectors) = 'string'
    LOOP
        val := r.cold_sectors;
        iterations := 0;
        WHILE jsonb_typeof(val) = 'string' AND iterations < 5 LOOP
            val := (val #>> '{}')::jsonb;
            iterations := iterations + 1;
        END LOOP;
        IF jsonb_typeof(val) IN ('array', 'object') THEN
            UPDATE rotation_evaluations SET cold_sectors = val WHERE id = r.id;
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 6. midday_checks.recommendation_overrides
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
    val JSONB;
    iterations INT;
BEGIN
    FOR r IN
        SELECT id, recommendation_overrides
        FROM midday_checks
        WHERE jsonb_typeof(recommendation_overrides) = 'string'
    LOOP
        val := r.recommendation_overrides;
        iterations := 0;
        WHILE jsonb_typeof(val) = 'string' AND iterations < 5 LOOP
            val := (val #>> '{}')::jsonb;
            iterations := iterations + 1;
        END LOOP;
        IF jsonb_typeof(val) IN ('array', 'object') THEN
            UPDATE midday_checks
            SET recommendation_overrides = val
            WHERE id = r.id;
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 7. strategy_directives.constraints (legacy rows, code is correct now)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
    val JSONB;
    iterations INT;
BEGIN
    FOR r IN
        SELECT scan_date, constraints
        FROM strategy_directives
        WHERE jsonb_typeof(constraints) = 'string'
    LOOP
        val := r.constraints;
        iterations := 0;
        WHILE jsonb_typeof(val) = 'string' AND iterations < 5 LOOP
            val := (val #>> '{}')::jsonb;
            iterations := iterations + 1;
        END LOOP;
        IF jsonb_typeof(val) IN ('object', 'array') THEN
            UPDATE strategy_directives
            SET constraints = val
            WHERE scan_date = r.scan_date;
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 8. Post-assertions — fail loudly if anything is still broken
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    broken RECORD;
    offenders INT := 0;
BEGIN
    FOR broken IN
        SELECT 'macro_metrics.geopolitical_shock' AS col, COUNT(*) AS n
        FROM macro_metrics WHERE jsonb_typeof(geopolitical_shock) = 'string'
        UNION ALL
        SELECT 'alerts.alert_metadata', COUNT(*)
        FROM alerts WHERE jsonb_typeof(alert_metadata) = 'string'
        UNION ALL
        SELECT 'alert_conditions.params', COUNT(*)
        FROM alert_conditions WHERE jsonb_typeof(params) = 'string'
        UNION ALL
        SELECT 'morning_position_alerts.dissenting_views', COUNT(*)
        FROM morning_position_alerts WHERE jsonb_typeof(dissenting_views) = 'string'
        UNION ALL
        SELECT 'rotation_evaluations.hot_sectors', COUNT(*)
        FROM rotation_evaluations WHERE jsonb_typeof(hot_sectors) = 'string'
        UNION ALL
        SELECT 'rotation_evaluations.cold_sectors', COUNT(*)
        FROM rotation_evaluations WHERE jsonb_typeof(cold_sectors) = 'string'
        UNION ALL
        SELECT 'midday_checks.recommendation_overrides', COUNT(*)
        FROM midday_checks WHERE jsonb_typeof(recommendation_overrides) = 'string'
        UNION ALL
        SELECT 'strategy_directives.constraints', COUNT(*)
        FROM strategy_directives WHERE jsonb_typeof(constraints) = 'string'
    LOOP
        IF broken.n > 0 THEN
            RAISE WARNING 'Backfill left % rows on %', broken.n, broken.col;
            offenders := offenders + broken.n;
        END IF;
    END LOOP;
    IF offenders > 0 THEN
        RAISE EXCEPTION
            'JSONB backfill 307 left % rows with jsonb_typeof=string — see warnings',
            offenders;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 9. One-shot backfill: orphan geopolitical narratives (RC1)
--    Links Apr 2026 orphan rows to `hormuz_closure_2026` so the morning
--    brief stops showing empty `related_catalysts`. After RC1 lands the
--    catalysts agent creates geopolitical catalysts with article links and
--    the normal SQL join (narratives ↔ catalyst_articles) takes over.
-- ---------------------------------------------------------------------------
UPDATE narratives
SET related_catalysts = ARRAY['hormuz_closure_2026']
WHERE narrative_type = 'geopolitical'
  AND (related_catalysts IS NULL OR cardinality(related_catalysts) = 0)
  AND status = 'active'
  AND (
      theme ILIKE '%hormuz%'
      OR theme ILIKE '%iran%war%'
      OR theme ILIKE '%trump%blockade%'
      OR theme ILIKE '%middle east%oil%'
  );

COMMIT;
