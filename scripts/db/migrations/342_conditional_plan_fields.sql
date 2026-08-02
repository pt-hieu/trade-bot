-- 342_conditional_plan_fields.sql
-- Conditional WATCH/WAIT plans + alert→BUY closure (SWI-NN).
--
-- Adds 5 columns to daily_recommendations carrying the structured plan
-- attached to non-BUY rows: trigger_price_vnd, plan_shape, invalidation_note,
-- gate_floor_at_build, gate_passes_at_build. Also adds a unique partial
-- index that lets run_alert_analysis.py upsert source='alert_fire' rows
-- idempotently when a conditional alert triggers.
--
-- TRADEOFF: conditional-plan fields collocated on daily_recommendations
-- rather than in a child table. Justification: atomic insert with the
-- recommendation row, zero JOINs in alert_monitor reads, simple renderer
-- queries. Same call previously made by migrations 312 (atr/trail) and
-- 317 (plan_type). Revisit if plan_shape enum exceeds 6 states or readers
-- filtering on `plan_shape IS NOT NULL` exceed 3 call sites.

BEGIN;

ALTER TABLE daily_recommendations
  ADD COLUMN IF NOT EXISTS trigger_price_vnd     BIGINT,
  ADD COLUMN IF NOT EXISTS plan_shape            TEXT,
  ADD COLUMN IF NOT EXISTS invalidation_note     TEXT,
  ADD COLUMN IF NOT EXISTS gate_floor_at_build   NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS gate_passes_at_build  BOOLEAN;

ALTER TABLE daily_recommendations
  DROP CONSTRAINT IF EXISTS daily_recs_plan_shape_chk;
ALTER TABLE daily_recommendations
  ADD CONSTRAINT daily_recs_plan_shape_chk
  CHECK (plan_shape IS NULL OR plan_shape IN
    ('BREAKOUT','PULLBACK','TREND_PULLBACK','BOUNCE','MEAN_REVERT','NONE'));

ALTER TABLE daily_recommendations
  DROP CONSTRAINT IF EXISTS daily_recs_plan_shape_action_chk;
ALTER TABLE daily_recommendations
  ADD CONSTRAINT daily_recs_plan_shape_action_chk
  CHECK (
    plan_shape IS NULL
    OR plan_shape = 'NONE'
    OR (action::text IN ('WATCH','WAIT') AND trigger_price_vnd IS NOT NULL)
  );

CREATE INDEX IF NOT EXISTS idx_daily_recs_plan_shape
  ON daily_recommendations (plan_shape) WHERE plan_shape IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_daily_recs_alert_fire
  ON daily_recommendations (record_id, ticker)
  WHERE source = 'alert_fire';

COMMIT;

INSERT INTO schema_migrations (version)
VALUES ('342_conditional_plan_fields')
ON CONFLICT DO NOTHING;
