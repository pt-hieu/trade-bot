-- Alert system for automated price/technical monitoring
-- Agents register alerts -> Lightsail daemon polls -> Telegram notifications

CREATE TABLE alerts (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    condition_type VARCHAR(30) NOT NULL,  -- price_below, price_above, rsi_below, rsi_above, volume_spike
    condition_value NUMERIC,
    condition_extra JSONB DEFAULT '{}',
    action_type VARCHAR(20) NOT NULL DEFAULT 'notify',  -- notify, notify_and_analyze
    source VARCHAR(30) NOT NULL,          -- morning_brief, midday, position_monitor, longterm, manual
    source_date DATE NOT NULL,
    rationale TEXT,
    recommended_action VARCHAR(10),       -- BUY, TRIM, EXIT, ADD, WATCH
    entry_price NUMERIC,
    stop_price NUMERIC,
    target_price NUMERIC,
    status VARCHAR(15) NOT NULL DEFAULT 'active',  -- active, triggered, expired, cancelled
    priority VARCHAR(10) NOT NULL DEFAULT 'normal', -- high, normal, low
    triggered_at TIMESTAMPTZ,
    triggered_value NUMERIC,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_active ON alerts(status, ticker) WHERE status = 'active';
CREATE INDEX idx_alerts_source ON alerts(source_date, source);

CREATE TABLE alert_history (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT REFERENCES alerts(id),
    event_type VARCHAR(20) NOT NULL,  -- created, triggered, expired, cancelled, analyzed
    event_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alert_history_alert ON alert_history(alert_id);
