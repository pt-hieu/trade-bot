-- Migration 245: Backfill HOLD won values and entry_hit_rate NULLs
--
-- 1. Flip won=false→true for HOLD evals where day_change is between -2.0% and -1.0%
--    (old threshold was -1.0%, new threshold is -2.0%)
-- 2. Set entry_hit_rate=NULL on daily_records where no entry actions existed
-- 3. Recompute win_rate on daily_records from corrected daily_evaluations.won

-- Step 1: Fix HOLD evaluations scored with old -1.0% threshold
UPDATE daily_evaluations
SET won = true
WHERE status = 'HOLD'
  AND recommendation NOT IN ('TRIM', 'EXIT')
  AND day_change IS NOT NULL
  AND day_change >= -2.0
  AND day_change < -1.0
  AND won = false;

-- Step 2: NULL out entry_hit_rate where no BUY/ADD/LIMIT_BUY existed
UPDATE daily_records
SET entry_hit_rate = NULL
WHERE id IN (
    SELECT dr.id
    FROM daily_records dr
    WHERE dr.entry_hit_rate IS NOT NULL
      AND dr.entry_hit_rate = 0
      AND NOT EXISTS (
          SELECT 1 FROM daily_evaluations de
          WHERE de.record_id = dr.id
            AND de.recommendation IN ('BUY', 'ADD', 'LIMIT_BUY')
      )
);

-- Step 3: Recompute win_rate from corrected won values
UPDATE daily_records dr
SET win_rate = sub.new_win_rate
FROM (
    SELECT
        de.record_id,
        ROUND(
            COUNT(*) FILTER (WHERE de.won = true)::numeric
            / NULLIF(COUNT(*) FILTER (WHERE de.won IS NOT NULL), 0)
            * 100, 2
        ) AS new_win_rate
    FROM daily_evaluations de
    GROUP BY de.record_id
) sub
WHERE dr.id = sub.record_id
  AND dr.win_rate IS DISTINCT FROM sub.new_win_rate;
