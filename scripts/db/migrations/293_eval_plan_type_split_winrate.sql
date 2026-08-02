-- Migration 293: Add plan_type to daily_evaluations + split win rates in learnings_summary
--
-- Problem: won=true on -12% HOLD positions inflates win_rate to ~100%,
-- disabling position sizing safety net. Swing and longterm have different
-- "won" semantics, so win_rate must be split.

-- 1. Add plan_type column to daily_evaluations
ALTER TABLE daily_evaluations
ADD COLUMN IF NOT EXISTS plan_type TEXT;

-- 2. Backfill from trades_calculated (has temporal coverage via entry_date/exit_date)
-- NOT from portfolio_holdings (live snapshot only — misses closed positions)
UPDATE daily_evaluations de
SET plan_type = COALESCE(
    (SELECT tc.plan_type FROM trades_calculated tc
     WHERE tc.ticker = de.ticker
       AND tc.entry_date <= dr.record_date
       AND (tc.exit_date IS NULL OR tc.exit_date >= dr.record_date)
     ORDER BY tc.entry_date DESC LIMIT 1),
    'SWING'
)
FROM daily_records dr
WHERE dr.id = de.record_id
  AND de.plan_type IS NULL;

-- 3. Any remaining NULLs (no trade match) default to SWING
UPDATE daily_evaluations
SET plan_type = 'SWING'
WHERE plan_type IS NULL;

-- 4. Add split win rate columns to learnings_summary
ALTER TABLE learnings_summary
ADD COLUMN IF NOT EXISTS swing_win_rate NUMERIC,
ADD COLUMN IF NOT EXISTS longterm_win_rate NUMERIC,
ADD COLUMN IF NOT EXISTS swing_sample_size INTEGER;
