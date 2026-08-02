-- Persist the day's global_risk_regime alongside daily_records so
-- pipeline-review bundles (and downstream audits) can answer "what
-- regime was the pipeline operating under?" without cross-joining
-- macro_metrics. MON-2026-04-14 observability gap.
ALTER TABLE daily_records
    ADD COLUMN IF NOT EXISTS global_risk_regime TEXT;

COMMENT ON COLUMN daily_records.global_risk_regime IS
    'CALM | MODERATE | CAUTIOUS | ELEVATED | CRISIS';
