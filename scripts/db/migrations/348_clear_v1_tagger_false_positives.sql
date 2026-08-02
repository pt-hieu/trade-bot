BEGIN;
-- SWI-390: clear v1 substring-baseline tagger residue.
-- Cleared: every row whose affected_tickers was *only* written by the deleted
-- INSERT-time regex baseline and never overlaid by Stage-2.
--
-- Two writers can set sentiment_tickers — news_v2_persist.py:125 ($4 = the
-- extractor's affected_tickers), and update_content.py:112,129
-- (write_article_sentiments uses `sentiment_tickers = COALESCE(
-- a.affected_tickers, a.sentiment_tickers)`). The second writer
-- *promotes* the v1 baseline tag into sentiment_tickers whenever the
-- sentiment scorer runs on a row Stage-2 hasn't touched — so a
-- `sentiment_tickers IS NULL` sentinel alone undercleared.
--
-- Combined sentinel: Stage-2 truly never wrote ⇔
--   (sentiment_tickers IS NULL) OR (sentiment_tickers = affected_tickers
--   AND the equality came from the COALESCE promotion, not from a real
--   Stage-2 write that happened to match — those are negligibly rare).
-- This also covers the Stage-1-routed + Stage-2-abstained case:
-- abstain → no UPDATE → sentiment_tickers stays NULL → matched.
-- Bonus: the same UPDATE clears the COALESCE-polluted sentiment_tickers
-- so downstream readers (sentiment_score consumers) don't see ghost tags.
UPDATE articles
SET affected_tickers = '{}'::text[],
    sentiment_tickers = CASE
      WHEN sentiment_tickers = affected_tickers THEN NULL
      ELSE sentiment_tickers
    END
WHERE array_length(affected_tickers, 1) > 0
  AND (sentiment_tickers IS NULL OR sentiment_tickers = affected_tickers);
INSERT INTO schema_migrations (version)
VALUES ('348_clear_v1_tagger_false_positives')
ON CONFLICT DO NOTHING;
COMMIT;
