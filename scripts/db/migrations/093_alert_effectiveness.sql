-- 093_alert_effectiveness.sql
-- Close the alert-to-trade feedback loop.
-- Tracks which triggered alerts led to actual trades and their P/L outcomes.

ALTER TABLE trades_calculated ADD COLUMN IF NOT EXISTS source_alert_id BIGINT REFERENCES alerts(id);
ALTER TABLE trades_calculated ADD COLUMN IF NOT EXISTS alert_triggered_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS alert_effectiveness (
    id SERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES alerts(id),
    trade_id UUID REFERENCES trades_calculated(id),
    ticker VARCHAR(10) NOT NULL,
    alert_source VARCHAR(50),
    recommended_action VARCHAR(20),
    actual_action VARCHAR(20),
    was_converted BOOLEAN DEFAULT FALSE,
    pnl_pct FLOAT,
    scan_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_effectiveness_date ON alert_effectiveness(scan_date DESC);
CREATE INDEX IF NOT EXISTS idx_alert_effectiveness_alert ON alert_effectiveness(alert_id);

COMMENT ON TABLE alert_effectiveness IS 'Alert-to-trade matching for feedback loop analysis. Populated by retrospective.py.';
