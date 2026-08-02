-- Migration 205: Backfill predicted_rr and stop_buffer_pct from recommendation prices
-- Type: Data-only (default DATABASE_URL works)
--
-- Backfills calibration fields that can be computed from stored price data.
-- entry_gap_pct, actual_max_rr (need eod_high/low), and ATR fields (need API) cannot
-- be backfilled — they populate naturally going forward.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/205_backfill_eval_calibration.sql

-- Backfill predicted_rr = (target - entry) / (entry - stop)
UPDATE daily_evaluations de
SET predicted_rr = ROUND(
    (dr.target_price_vnd - dr.entry_price_vnd)::NUMERIC /
    (dr.entry_price_vnd - dr.stop_price_vnd)::NUMERIC, 2
)
FROM daily_recommendations dr
WHERE dr.record_id = de.record_id
  AND dr.ticker = de.ticker
  AND de.predicted_rr IS NULL
  AND dr.entry_price_vnd IS NOT NULL
  AND dr.stop_price_vnd IS NOT NULL
  AND dr.target_price_vnd IS NOT NULL
  AND dr.entry_price_vnd > 0
  AND dr.stop_price_vnd > 0
  AND (dr.entry_price_vnd - dr.stop_price_vnd) > 0;

-- Backfill stop_buffer_pct = |entry - stop| / entry * 100
UPDATE daily_evaluations de
SET stop_buffer_pct = ROUND(
    ABS(dr.entry_price_vnd - dr.stop_price_vnd)::NUMERIC /
    dr.entry_price_vnd::NUMERIC * 100, 2
)
FROM daily_recommendations dr
WHERE dr.record_id = de.record_id
  AND dr.ticker = de.ticker
  AND de.stop_buffer_pct IS NULL
  AND dr.entry_price_vnd IS NOT NULL
  AND dr.stop_price_vnd IS NOT NULL
  AND dr.entry_price_vnd > 0
  AND dr.stop_price_vnd > 0;
