-- 324_narrative_dedup_merge.sql
-- Fix 6 of the narrative+catalyst systemic plan (2026-04-21).
-- Merge same-day active narrative pairs with overlapping ticker/sector
-- sets AND opposite sentiment signs (|sentiment| > 0.15 on both sides).
-- These pairs (e.g. Hormuz-rise / Hormuz-fall) are created by the
-- embedding-only matcher before Fix 6's direction guard was active.
--
-- Strategy: mark the LOWER-conviction narrative as `stale` and note the
-- merge into the remaining narrative's summary. Keeps articles attached
-- to their original narrative_id (articles.narrative_id is not rewritten)
-- so historical audit stays intact — downstream briefings only read
-- `status='active'` rows so the stale side stops showing up.

BEGIN;

WITH active_pairs AS (
  SELECT
    a.id AS winner_id,
    a.narrative_key AS winner_key,
    a.conviction_score AS winner_conviction,
    b.id AS loser_id,
    b.narrative_key AS loser_key,
    b.conviction_score AS loser_conviction,
    a.avg_sentiment AS a_sent,
    b.avg_sentiment AS b_sent
  FROM narratives a
  JOIN narratives b ON b.id > a.id
  WHERE a.status = 'active'
    AND b.status = 'active'
    AND ABS(a.avg_sentiment) > 0.15
    AND ABS(b.avg_sentiment) > 0.15
    AND SIGN(a.avg_sentiment) <> SIGN(b.avg_sentiment)
    AND (a.affected_tickers && b.affected_tickers
         OR a.affected_sectors && b.affected_sectors)
    -- Same-day window — 14 days as per plan
    AND a.first_seen >= CURRENT_DATE - INTERVAL '14 days'
    AND b.first_seen >= CURRENT_DATE - INTERVAL '14 days'
),
resolved AS (
  SELECT
    CASE WHEN winner_conviction >= loser_conviction THEN winner_id ELSE loser_id END AS keep_id,
    CASE WHEN winner_conviction >= loser_conviction THEN loser_id ELSE winner_id END AS drop_id,
    CASE WHEN winner_conviction >= loser_conviction THEN winner_key ELSE loser_key END AS keep_key,
    CASE WHEN winner_conviction >= loser_conviction THEN loser_key ELSE winner_key END AS drop_key
  FROM active_pairs
)
UPDATE narratives n
SET status = 'stale',
    maturity = 'stale',
    summary = COALESCE(n.summary, '')
           || ' | Fix 6 (2026-04-21): merged into narrative "'
           || (SELECT keep_key FROM resolved r WHERE r.drop_id = n.id LIMIT 1)
           || '" (opposite-sentiment duplicate).',
    updated_at = NOW()
WHERE n.id IN (SELECT drop_id FROM resolved);

-- Audit.
SELECT COUNT(*) AS stale_merged_rows
FROM narratives
WHERE status = 'stale'
  AND summary LIKE '%Fix 6 (2026-04-21)%';

COMMIT;
