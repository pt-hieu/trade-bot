-- 334_news_pipeline_audit_fixes.sql
-- News pipeline P0/P1 audit fixes (SWI-192 — children SWI-197/198/199/201/202).
--
-- Sequenced strictly:
--   1. Strip non-VN tickers from articles + narratives (last 30d, forward-only).
--   2. Reclassify the 14 known-mistyped active catalysts via pattern UPDATEs.
--   3. Pre-audit + delete orphan catalyst_news_signals rows.
--   4. DROP+RECREATE FK with ON UPDATE/DELETE CASCADE.
--   5. Widen catalysts.catalyst_key to VARCHAR(64).
--   6. Recompose catalyst_key bit-for-bit identical to Python composer.
--   7. Add unique_article_count column for SWI-201 spike dedup.
--   7b. catalyst_rejections audit table (SWI-198 Lever E).
--   8. CHECK constraint on catalyst_type allowlist (no enum to widen).

BEGIN;

-- ---------------------------------------------------------------------------
-- Step 1 — strip non-VN tickers (forward-only). Mig 329 did the historic pass;
-- this re-runs against the last 30 days to catch anything that slipped in
-- before SWI-197 took effect.
-- ---------------------------------------------------------------------------
WITH vn_universe AS (
    SELECT ticker FROM company_profiles
    UNION
    SELECT ticker FROM stocks WHERE is_active = TRUE
)
UPDATE articles a
SET affected_tickers = (
    SELECT COALESCE(ARRAY_AGG(t), ARRAY[]::TEXT[])
    FROM unnest(a.affected_tickers) t
    WHERE t = 'VN-INDEX' OR t IN (SELECT ticker FROM vn_universe)
)
WHERE a.published_at >= NOW() - INTERVAL '30 days'
  AND a.affected_tickers IS NOT NULL
  AND a.affected_tickers <> ARRAY[]::TEXT[];

WITH vn_universe AS (
    SELECT ticker FROM company_profiles
    UNION
    SELECT ticker FROM stocks WHERE is_active = TRUE
)
UPDATE narratives n
SET affected_tickers = (
    SELECT COALESCE(ARRAY_AGG(t), ARRAY[]::TEXT[])
    FROM unnest(n.affected_tickers) t
    WHERE t = 'VN-INDEX' OR t IN (SELECT ticker FROM vn_universe)
)
WHERE n.last_seen >= CURRENT_DATE - INTERVAL '30 days'
  AND n.affected_tickers IS NOT NULL
  AND n.affected_tickers <> ARRAY[]::TEXT[];

-- ---------------------------------------------------------------------------
-- Step 2 — reclassify the 14 known-mistyped active catalysts. Idempotent:
-- updates only rows currently tagged 'regulatory' so a re-run is a no-op.
-- ---------------------------------------------------------------------------
UPDATE catalysts
SET catalyst_type = 'geopolitical'
WHERE status = 'active'
  AND catalyst_type = 'regulatory'
  AND (
       event ~* '\bOPEC\+?\b'
    OR event ~* '\b(?:UAE|Saudi|Qatar) (?:quits|leaves|exits) OPEC'
    OR event ~* '\bHormuz\b'
    OR event ~* '\b(?:IRGC|Houthi)\b'
    OR event ~* '\boil supply (?:loss|cut|disruption)\b'
    OR event ~* '\bred sea (?:transit|attack|crisis|disruption)\b'
    OR event ~* '\btanker (?:hijack|seizure)\b'
    OR event ~* 'iran(?:-|\s)(?:war|israel|russia|conflict|crisis)'
  );

UPDATE catalysts
SET catalyst_type = 'macro'
WHERE status = 'active'
  AND catalyst_type = 'regulatory'
  AND (
       event ~* '\bIMF\b.*\b(?:GDP|growth|forecast)\b'
    OR event ~* '\bFed\b.*(?:nominee|chair candidate|hire|fire)'
    OR event ~* '(?:Trump|White House).*(?:Fed|Powell)'
  );

UPDATE catalysts
SET catalyst_type = 'commodity'
WHERE status = 'active'
  AND catalyst_type = 'regulatory'
  AND (
       event ~* '\bIdemitsu\b'
    OR event ~* '\bLong Son petrochemical\b'
    OR event ~* '\bLNG (?:cargo|shipment|export)\b'
  );

-- ---------------------------------------------------------------------------
-- Step 3 — pre-audit + delete orphan catalyst_news_signals rows.
-- Truncated catalyst_key values in signals can't be remapped without the
-- source event text, so we drop them; the spike detector recomputes baseline
-- from the surviving rows on the next run.
-- ---------------------------------------------------------------------------
DO $$
DECLARE orphan_count int;
BEGIN
  SELECT COUNT(*) INTO orphan_count
  FROM catalyst_news_signals s
  LEFT JOIN catalysts c USING (catalyst_key)
  WHERE c.catalyst_key IS NULL;
  RAISE NOTICE 'Orphan catalyst_news_signals rows: %', orphan_count;
END $$;

DELETE FROM catalyst_news_signals
WHERE catalyst_key NOT IN (SELECT catalyst_key FROM catalysts);

-- ---------------------------------------------------------------------------
-- Step 4 — DROP+RECREATE FK with ON UPDATE CASCADE so the recompose UPDATE
-- in step 6 can flow through children. catalyst_articles already cascades
-- (mig 325) — we re-add idempotently for clarity.
-- ---------------------------------------------------------------------------
ALTER TABLE catalyst_news_signals
  DROP CONSTRAINT IF EXISTS catalyst_news_signals_catalyst_key_fkey;

ALTER TABLE catalyst_news_signals
  ADD CONSTRAINT catalyst_news_signals_catalyst_key_fkey
  FOREIGN KEY (catalyst_key)
  REFERENCES catalysts(catalyst_key)
  ON UPDATE CASCADE
  ON DELETE CASCADE;

ALTER TABLE catalyst_articles
  DROP CONSTRAINT IF EXISTS catalyst_articles_catalyst_key_fkey;

ALTER TABLE catalyst_articles
  ADD CONSTRAINT catalyst_articles_catalyst_key_fkey
  FOREIGN KEY (catalyst_key)
  REFERENCES catalysts(catalyst_key)
  ON UPDATE CASCADE
  ON DELETE CASCADE;

-- ---------------------------------------------------------------------------
-- Step 5 — widen catalysts.catalyst_key to VARCHAR(64). Children inherit
-- via the FK definition; explicit widen so child column types match.
-- ---------------------------------------------------------------------------
ALTER TABLE catalysts ALTER COLUMN catalyst_key TYPE VARCHAR(64);
ALTER TABLE catalyst_news_signals ALTER COLUMN catalyst_key TYPE VARCHAR(64);
ALTER TABLE catalyst_articles ALTER COLUMN catalyst_key TYPE VARCHAR(64);

-- ---------------------------------------------------------------------------
-- Step 6 — recompose catalyst_key. Bit-identical to
-- ``shared/rules/catalyst_key.compose_catalyst_key``: lower → non-alnum
-- collapsed to ``_`` → strip leading/trailing ``_`` → cap 32 chars
-- → append ``_<md5_8>``.
-- FK cascade propagates the rename to catalyst_news_signals.catalyst_key
-- and catalyst_articles.catalyst_key.
-- ---------------------------------------------------------------------------
UPDATE catalysts
SET catalyst_key =
    COALESCE(
        NULLIF(
            substr(
                trim(both '_' from regexp_replace(lower(event), '[^a-z0-9]+', '_', 'g')),
                1, 32
            ),
            ''
        ),
        'event'
    )
    || '_' || substr(md5(event), 1, 8);

-- ---------------------------------------------------------------------------
-- Step 7 — unique_article_count column for SWI-201. Existing rows leave
-- the column NULL; the reader COALESCEs to article_count for back-compat.
-- ---------------------------------------------------------------------------
ALTER TABLE catalyst_news_signals
    ADD COLUMN IF NOT EXISTS unique_article_count INTEGER NULL;

-- ---------------------------------------------------------------------------
-- Step 7b — catalyst_rejections audit table (SWI-198 Lever E).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS catalyst_rejections (
    id SERIAL PRIMARY KEY,
    event TEXT NOT NULL,
    candidate_type VARCHAR(50),
    reason VARCHAR(50) NOT NULL,
    scan_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_catalyst_rejections_scan_date
    ON catalyst_rejections (scan_date);

-- ---------------------------------------------------------------------------
-- Step 8 — catalyst_type CHECK constraint. Column is VARCHAR(50) (mig 126),
-- not a Postgres enum, so no ALTER TYPE ADD VALUE needed. Drift guard test
-- in tests/shared/rules/test_catalyst_classifier_extensions.py asserts the
-- Python `_VALID_TYPES` literal matches this allowlist.
-- ---------------------------------------------------------------------------
DO $$
DECLARE bad_count int;
BEGIN
  SELECT COUNT(*) INTO bad_count FROM catalysts
  WHERE catalyst_type IS NOT NULL
    AND catalyst_type NOT IN
      ('regulatory','earnings','macro','rating','geopolitical',
       'corporate_action','legal','commodity','unclassified');
  IF bad_count > 0 THEN
    RAISE NOTICE 'Reclassifying % rows outside allowlist to unclassified', bad_count;
    UPDATE catalysts SET catalyst_type = 'unclassified'
    WHERE catalyst_type IS NOT NULL
      AND catalyst_type NOT IN
        ('regulatory','earnings','macro','rating','geopolitical',
         'corporate_action','legal','commodity','unclassified');
  END IF;
END $$;

ALTER TABLE catalysts
    DROP CONSTRAINT IF EXISTS catalyst_type_allowed;

ALTER TABLE catalysts
    ADD CONSTRAINT catalyst_type_allowed
    CHECK (
      catalyst_type IS NULL
      OR catalyst_type IN
        ('regulatory','earnings','macro','rating','geopolitical',
         'corporate_action','legal','commodity','unclassified')
    );

-- ---------------------------------------------------------------------------
-- Record migration.
-- ---------------------------------------------------------------------------
INSERT INTO schema_migrations (version)
VALUES ('334_news_pipeline_audit_fixes')
ON CONFLICT DO NOTHING;

COMMIT;
