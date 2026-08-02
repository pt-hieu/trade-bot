-- 337_narrative_same_sentiment_merge.sql
-- SWI-74 Layer 2: drain the same-sentiment duplicate backlog.
--
-- Migration 324 only merged opposite-sentiment same-day pairs; every
-- cluster cited in the SWI-74 evidence (Iran/Hormuz/oil x ~140 rows,
-- gold_price_*, vietnam_market_upgrade_*, *stalled_projects*,
-- *admin_reform_*, plus near-duplicate key pairs like
-- iran_us_peace_talks_islamabad / us_iran_peace_talks_islamabad) is
-- same-sentiment, so 324 never reached them.
--
-- POSTWRITE_MERGE = 0.82 — cited from
--   scripts/shared/rules/narrative_thresholds.py
-- A unit test (test_narrative_threshold_parity) regex-extracts the
-- cosine literal below and asserts equality with the Python constant
-- (per project_schema_migrations_guard.md).
--
-- Survivor pick: conviction_score DESC, article_count DESC,
-- first_seen ASC. Losers: status='stale', maturity='stale',
-- merged_into = winner.id, summary tagged with audit marker.
--
-- Same transaction also backfills `merged_into` for migration-324
-- historical merges by parsing the
--   "Fix 6 (2026-04-21): merged into narrative ..."
-- summary marker — inverts text → FK so historical audit joins work.

BEGIN;

-- =========================================================================
-- Part 1: Same-sentiment same-day merge.
-- =========================================================================
WITH active_pairs AS (
  SELECT
    a.id AS a_id,
    a.narrative_key AS a_key,
    a.conviction_score AS a_conviction,
    a.article_count AS a_count,
    a.first_seen AS a_first_seen,
    b.id AS b_id,
    b.narrative_key AS b_key,
    b.conviction_score AS b_conviction,
    b.article_count AS b_count,
    b.first_seen AS b_first_seen
  FROM narratives a
  JOIN narratives b ON b.id > a.id
  WHERE a.status = 'active'
    AND b.status = 'active'
    AND a.narrative_type IS NOT NULL
    AND a.narrative_type = b.narrative_type
    AND ((a.affected_tickers && b.affected_tickers)
         OR (a.affected_sectors && b.affected_sectors))
    AND a.centroid_embedding IS NOT NULL
    AND b.centroid_embedding IS NOT NULL
    AND (1 - (a.centroid_embedding <=> b.centroid_embedding)) >= 0.82
    AND a.first_seen >= CURRENT_DATE - INTERVAL '14 days'
    AND b.first_seen >= CURRENT_DATE - INTERVAL '14 days'
),
ranked_pairs AS (
  SELECT
    CASE
      WHEN (a_conviction, a_count, -EXTRACT(EPOCH FROM a_first_seen))
         >= (b_conviction, b_count, -EXTRACT(EPOCH FROM b_first_seen))
      THEN a_id ELSE b_id
    END AS keep_id,
    CASE
      WHEN (a_conviction, a_count, -EXTRACT(EPOCH FROM a_first_seen))
         >= (b_conviction, b_count, -EXTRACT(EPOCH FROM b_first_seen))
      THEN b_id ELSE a_id
    END AS drop_id,
    CASE
      WHEN (a_conviction, a_count, -EXTRACT(EPOCH FROM a_first_seen))
         >= (b_conviction, b_count, -EXTRACT(EPOCH FROM b_first_seen))
      THEN a_key ELSE b_key
    END AS keep_key
  FROM active_pairs
),
-- Pick a single winner per loser (transitive clusters): the highest-
-- ranked keep_id wins. Subqueries in UPDATE require deterministic 1:1.
resolved AS (
  SELECT DISTINCT ON (drop_id)
    drop_id,
    keep_id,
    keep_key
  FROM ranked_pairs
  -- Stable winner pick: prefer the keep_id with the highest conviction
  -- among all candidates pointing at this drop_id.
  ORDER BY drop_id,
           (SELECT n.conviction_score FROM narratives n WHERE n.id = ranked_pairs.keep_id) DESC,
           keep_id ASC
)
UPDATE narratives n
SET status = 'stale',
    maturity = 'stale',
    merged_into = r.keep_id,
    summary = COALESCE(n.summary, '')
           || ' | SWI-74 (2026-05-01): merged into narrative "'
           || r.keep_key
           || '" (same-sentiment duplicate, cosine >= 0.82).',
    updated_at = NOW()
FROM resolved r
WHERE n.id = r.drop_id
  AND n.merged_into IS NULL;

-- =========================================================================
-- Part 2: Backfill merged_into for migration-324 historical merges.
-- The 324 migration tagged the loser's summary with the winner's
-- narrative_key but never populated the FK column (text-only audit).
-- This subquery inverts the text → FK so downstream readers can join.
-- =========================================================================
UPDATE narratives loser
SET merged_into = winner.id,
    updated_at = NOW()
FROM narratives winner
WHERE loser.merged_into IS NULL
  AND loser.status = 'stale'
  AND loser.summary LIKE '%Fix 6 (2026-04-21)%'
  AND winner.narrative_key = (
        -- Extract the quoted narrative_key from the Fix 6 marker.
        SELECT (regexp_match(
                 loser.summary,
                 'Fix 6 \(2026-04-21\): merged into narrative "([^"]+)"'
               ))[1]
      );

-- =========================================================================
-- Audit.
-- =========================================================================
SELECT
  COUNT(*) FILTER (WHERE summary LIKE '%SWI-74 (2026-05-01)%') AS swi74_merged,
  COUNT(*) FILTER (WHERE summary LIKE '%Fix 6 (2026-04-21)%' AND merged_into IS NOT NULL) AS fix6_backfilled,
  COUNT(*) FILTER (WHERE merged_into IS NOT NULL) AS total_merged_into_set
FROM narratives;

COMMIT;
