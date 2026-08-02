-- Migration 312: ExitStrategy polymorphism fields.
--
-- Enables dual exit families derived from existing `strategy` column:
--   FIXED_TARGET (MEAN_REVERSION, BOUNCE, DIVERGENCE, PULLBACK) — uses target_price_vnd
--   ATR_TRAIL    (TREND, MOMENTUM, BREAKOUT)                    — uses atr_at_entry_vnd, trail_mult
--
-- No new enum. ExitStrategy dispatch reads `strategy` as single source of truth.
-- target_price_vnd already nullable on daily_recommendations — verified via
-- describe_table_schema. ATR_TRAIL rows persist target_price_vnd=NULL.

-- 1. daily_recommendations — trail-tracking fields for ATR_TRAIL family
ALTER TABLE daily_recommendations
    ADD COLUMN IF NOT EXISTS atr_at_entry_vnd BIGINT,
    ADD COLUMN IF NOT EXISTS trail_mult NUMERIC(4, 2);

COMMENT ON COLUMN daily_recommendations.atr_at_entry_vnd IS
    'Average True Range at entry (VND integer). Required for ATR_TRAIL recs, '
    'NULL for FIXED_TARGET. Used by retro and alert monitor to simulate the '
    'trailing stop via max(peak - trail_mult * ATR, hard_stop).';
COMMENT ON COLUMN daily_recommendations.trail_mult IS
    'Trailing stop multiplier (typically 2.5). Only set for ATR_TRAIL recs. '
    'NULL for FIXED_TARGET. The trailing stop = peak_price - trail_mult * ATR.';

-- 2. daily_evaluations — trail-exit outcome fields for retro
ALTER TABLE daily_evaluations
    ADD COLUMN IF NOT EXISTS trail_peak_vnd BIGINT,
    ADD COLUMN IF NOT EXISTS trail_exit_price_vnd BIGINT,
    ADD COLUMN IF NOT EXISTS trail_exit_date DATE,
    ADD COLUMN IF NOT EXISTS days_in_trade INTEGER;

COMMENT ON COLUMN daily_evaluations.trail_peak_vnd IS
    'Highest close reached during holding window for ATR_TRAIL recs. NULL '
    'for FIXED_TARGET. Used for trail-efficiency audit (peak vs exit gap).';
COMMENT ON COLUMN daily_evaluations.trail_exit_price_vnd IS
    'Exit price selected by trail simulator for ATR_TRAIL recs. May be the '
    'trailing-stop level, hard stop, or HOSE floor-lock level.';
COMMENT ON COLUMN daily_evaluations.trail_exit_date IS
    'Trading date on which the trail simulator marked the exit.';
COMMENT ON COLUMN daily_evaluations.days_in_trade IS
    'Number of trading days held — covers both FIXED_TARGET (entry→target/stop) '
    'and ATR_TRAIL (entry→trail exit). NULL when entry never hit.';

-- 3. Alert monitor (Lightsail) trail fields. Tables exist as
-- morning_position_alerts and midday_position_alerts. Both receive the
-- same columns so either surface can drive the trail monitor.
ALTER TABLE morning_position_alerts
    ADD COLUMN IF NOT EXISTS trail_peak_vnd BIGINT,
    ADD COLUMN IF NOT EXISTS trail_mult NUMERIC(4, 2),
    ADD COLUMN IF NOT EXISTS atr_at_entry_vnd BIGINT,
    ADD COLUMN IF NOT EXISTS strategy VARCHAR(32);

ALTER TABLE midday_position_alerts
    ADD COLUMN IF NOT EXISTS trail_peak_vnd BIGINT,
    ADD COLUMN IF NOT EXISTS trail_mult NUMERIC(4, 2),
    ADD COLUMN IF NOT EXISTS atr_at_entry_vnd BIGINT,
    ADD COLUMN IF NOT EXISTS strategy VARCHAR(32);

COMMENT ON COLUMN morning_position_alerts.strategy IS
    'Strategy from daily_recommendations.strategy. Drives ExitStrategy dispatch '
    'in the Lightsail alert monitor polling loop.';
COMMENT ON COLUMN midday_position_alerts.strategy IS
    'Strategy from daily_recommendations.strategy. Drives ExitStrategy dispatch '
    'in the Lightsail alert monitor polling loop.';

-- 4. Stratified-retro index. idx_daily_recs_strategy already exists on
-- daily_recommendations — no new index needed there.
CREATE INDEX IF NOT EXISTS idx_eval_strategy
    ON daily_evaluations(strategy)
    WHERE strategy IS NOT NULL;
