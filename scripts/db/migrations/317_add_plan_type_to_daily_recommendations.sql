-- 2026-04-21: Close the FPT cascade gap. Commit e8f5b814 added plan_type to
-- get_morning_recommendations SELECT but never shipped a migration, so every
-- read of daily_recommendations raises UndefinedColumnError. Retro compute_won
-- prefers rec.plan_type over the collapsed holdings fallback — without this
-- column the preference is a dead branch.
--
-- Backfill strategy:
--   MY_HOLDINGS recs -> join portfolio_holdings on ticker, prefer SWING
--     over LONGTERM when a ticker is dual-listed (matches the FPT incident's
--     swing-first collapse semantics for historic rows only).
--   everything else -> 'SWING' (sector picks, longterm watchlist alerts,
--     skips). Sector is a swing-trading pipeline; SWING is the right default.
--
-- After this migration the INSERT path in shared/neon/insert_records/_common.py
-- must also carry plan_type (see accompanying code change).

BEGIN;

ALTER TABLE daily_recommendations
    ADD COLUMN IF NOT EXISTS plan_type text;

-- Backfill MY_HOLDINGS rows from portfolio_holdings. SWING wins over LONGTERM
-- for dual-listed tickers to match historical behavior prior to migration 314.
WITH holdings_plan AS (
    SELECT DISTINCT ON (ticker) ticker, plan_type
    FROM portfolio_holdings
    ORDER BY ticker,
             CASE WHEN plan_type = 'SWING' THEN 0
                  WHEN plan_type = 'LONGTERM' THEN 1
                  ELSE 2 END
)
UPDATE daily_recommendations r
SET plan_type = h.plan_type
FROM holdings_plan h
WHERE r.ticker = h.ticker
  AND r.section = 'MY_HOLDINGS'
  AND r.plan_type IS NULL;

-- Longterm watchlist rows -> LONGTERM
UPDATE daily_recommendations
SET plan_type = 'LONGTERM'
WHERE section = 'LONG_TERM' AND plan_type IS NULL;

-- Everything else -> SWING (sector picks, skips, reconciliation, alerts)
UPDATE daily_recommendations
SET plan_type = 'SWING'
WHERE plan_type IS NULL;

-- Lock it down: all future rows must carry a value. Producers fail loudly if
-- they forget rather than silently writing NULL.
ALTER TABLE daily_recommendations
    ALTER COLUMN plan_type SET NOT NULL;

ALTER TABLE daily_recommendations
    ADD CONSTRAINT daily_recommendations_plan_type_check
    CHECK (plan_type IN ('SWING', 'LONGTERM'));

CREATE INDEX IF NOT EXISTS idx_daily_recs_plan_type
    ON daily_recommendations (plan_type);

COMMIT;
