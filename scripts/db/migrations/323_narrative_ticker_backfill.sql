-- 323_narrative_ticker_backfill.sql
-- Fix 5 of the narrative+catalyst systemic plan (2026-04-21).
-- Backfill active narratives' `affected_tickers` / `affected_sectors` from
-- the `narrative_updates` bridge join to `articles.affected_tickers` and
-- `articles.affected_sectors`. Previously narratives were created with a
-- ticker/sector snapshot at `_create_narrative` time and never updated,
-- so mature 17-article narratives could still show `affected_tickers=[]`.
--
-- Going forward, `shared/neon/narratives.update_narrative_on_article`
-- union-merges new tickers/sectors per article attachment — this migration
-- is one-shot to repair the accumulated backlog.

BEGIN;

-- Backfill affected_tickers from all linked articles, union-dedup.
UPDATE narratives n
SET affected_tickers = sub.tickers,
    updated_at = NOW()
FROM (
  SELECT nu.narrative_id,
         ARRAY(
           SELECT DISTINCT ticker
           FROM (
             SELECT UNNEST(a.affected_tickers) AS ticker
             FROM narrative_updates nu2
             JOIN articles a ON a.id = nu2.article_id
             WHERE nu2.narrative_id = nu.narrative_id
               AND a.affected_tickers IS NOT NULL
           ) t
           WHERE ticker IS NOT NULL AND ticker <> ''
         ) AS tickers
  FROM narrative_updates nu
  GROUP BY nu.narrative_id
) sub
WHERE n.id = sub.narrative_id
  AND n.status = 'active'
  AND ARRAY_LENGTH(sub.tickers, 1) > 0;

-- Note: articles table has no `affected_sectors` column (only
-- `affected_tickers`), so sector-backfill is not possible from the
-- narrative_updates bridge join. Sectors stay as-set at narrative
-- creation time; the `update_narrative_on_article` union-merge (Fix 5
-- code path) simply receives an empty sectors list until the articles
-- model gains sectors — harmless no-op.

-- Audit: expect empty_tickers count to drop.
SELECT
  COUNT(*) FILTER (WHERE affected_tickers = ARRAY[]::TEXT[]) AS empty_tickers,
  COUNT(*) AS total_active
FROM narratives
WHERE status = 'active';

COMMIT;
