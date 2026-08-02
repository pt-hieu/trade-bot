-- Migration 259: Narrative maturity + Catalyst lifecycle expansion + Article provenance bridge
-- Type: DDL (requires owner connection)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py 259_narrative_catalyst_redesign.sql

-- ── A. Narrative maturity column ────────────────────────────────────────────
ALTER TABLE narratives ADD COLUMN IF NOT EXISTS maturity VARCHAR(20) DEFAULT 'emerging';
CREATE INDEX IF NOT EXISTS idx_narratives_maturity ON narratives(maturity) WHERE status = 'active';

-- ── B. Catalyst lifecycle expansion ─────────────────────────────────────────
-- Migrate old 'completed' status BEFORE adding new constraint
ALTER TABLE catalysts DROP CONSTRAINT IF EXISTS catalysts_status_check;
UPDATE catalysts SET status = 'resolved' WHERE status = 'completed';
ALTER TABLE catalysts ADD CONSTRAINT catalysts_status_check
    CHECK (status IN ('active', 'monitoring', 'imminent', 'resolved', 'expired'));

-- Parseable date alongside existing freetext expected VARCHAR
ALTER TABLE catalysts ADD COLUMN IF NOT EXISTS expected_date DATE;
-- Staleness tracking
ALTER TABLE catalysts ADD COLUMN IF NOT EXISTS last_confirmed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_catalysts_expected_date ON catalysts(expected_date) WHERE expected_date IS NOT NULL;

-- ── C. Catalyst-articles bridge table ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS catalyst_articles (
    catalyst_key VARCHAR(60) NOT NULL REFERENCES catalysts(catalyst_key),
    article_id UUID NOT NULL,
    discovered_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (catalyst_key, article_id)
);
CREATE INDEX IF NOT EXISTS idx_catalyst_articles_article ON catalyst_articles(article_id);

-- ── D. Backfill narrative maturity from article_count + source_count ────────
UPDATE narratives SET maturity = CASE
    WHEN article_count >= 5 AND source_count >= 3 THEN 'mature'
    WHEN article_count >= 2 AND source_count >= 2 THEN 'confirmed'
    WHEN article_count >= 2 THEN 'developing'
    ELSE 'emerging'
END WHERE status = 'active';

UPDATE narratives SET maturity = 'stale' WHERE status = 'stale';

-- ── E. Tune half-lives for Vietnam market (slower info absorption) ──────────
UPDATE narratives SET half_life_days = 3
WHERE narrative_type = 'earnings' AND half_life_days = 2;

UPDATE narratives SET half_life_days = 7
WHERE narrative_type IN ('corporate', 'sector') AND half_life_days = 5;

UPDATE narratives SET half_life_days = 10
WHERE narrative_type = 'regulatory' AND half_life_days = 7;

-- ── F. Backfill catalyst columns ────────────────────────────────────────────
UPDATE catalysts SET last_confirmed_at = updated_at WHERE last_confirmed_at IS NULL;

UPDATE catalysts SET expected_date = CASE
    WHEN expected ~ '^\d{4}-\d{2}-\d{2}' THEN expected::DATE
    ELSE NULL
END WHERE expected_date IS NULL;

