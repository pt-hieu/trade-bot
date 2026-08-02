-- SWI-103: LLM-based article sentiment scorer with confidence channel.
-- Adds:
--   1. sentiment_confidence_enum
--   2. articles.sentiment_confidence
--   3. narratives.sentiment_confidence_roll (max-contributor rollup)
--   4. partial index on articles.sentiment_confidence
BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sentiment_confidence_enum') THEN
    CREATE TYPE sentiment_confidence_enum AS ENUM ('high', 'medium', 'low', 'abstain');
  END IF;
END $$;

ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS sentiment_confidence sentiment_confidence_enum;

ALTER TABLE narratives
  ADD COLUMN IF NOT EXISTS sentiment_confidence_roll sentiment_confidence_enum;

CREATE INDEX IF NOT EXISTS idx_articles_sentiment_conf
  ON articles (sentiment_confidence) WHERE sentiment_confidence IS NOT NULL;

COMMIT;
