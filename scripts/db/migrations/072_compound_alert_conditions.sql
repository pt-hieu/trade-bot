-- 072_compound_alert_conditions.sql
-- Replace single-condition columns with child table for compound conditions.
-- No backward compatibility — clears all existing alerts.

-- Clear existing data (clean slate, no compat needed)
DELETE FROM alert_history;
DELETE FROM alerts;

-- Drop old single-condition columns from alerts
ALTER TABLE alerts
  DROP COLUMN IF EXISTS condition_type,
  DROP COLUMN IF EXISTS condition_value,
  DROP COLUMN IF EXISTS condition_extra,
  DROP COLUMN IF EXISTS triggered_value;

-- Add compound condition support to alerts
ALTER TABLE alerts
  ADD COLUMN IF NOT EXISTS condition_logic VARCHAR(5) NOT NULL DEFAULT 'ALL',
  ADD COLUMN IF NOT EXISTS triggered_values JSONB;

-- New child table: one row per condition per alert
CREATE TABLE IF NOT EXISTS alert_conditions (
    id SERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    condition_type VARCHAR(30) NOT NULL,
    condition_value NUMERIC,
    params JSONB DEFAULT '{}',
    sort_order SMALLINT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alert_conditions_alert ON alert_conditions(alert_id);

COMMENT ON TABLE alert_conditions IS 'Individual conditions for compound alerts. All conditions in an alert must be met (condition_logic=ALL) or any (condition_logic=ANY).';
