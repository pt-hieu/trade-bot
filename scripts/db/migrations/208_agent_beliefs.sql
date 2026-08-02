-- Agent Beliefs: persistent per-agent per-ticker beliefs with accuracy tracking
-- Follows position_ensemble_votes pattern (UUID PK, date-keyed)

CREATE TABLE IF NOT EXISTS agent_beliefs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    record_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    agent_key VARCHAR(50) NOT NULL,
    ensemble_type VARCHAR(20) NOT NULL,

    -- The belief
    belief_narrative TEXT NOT NULL,
    direction VARCHAR(10) NOT NULL,
    bull_probability DECIMAL(5,4) NOT NULL,
    base_probability DECIMAL(5,4) NOT NULL,
    bear_probability DECIMAL(5,4) NOT NULL,
    price_target_vnd BIGINT,
    timeframe_days INTEGER NOT NULL DEFAULT 5,
    conviction DECIMAL(4,3) NOT NULL,

    -- Belief chain
    belief_status VARCHAR(12) NOT NULL,
    prior_belief_id UUID REFERENCES agent_beliefs(id),
    days_held INTEGER NOT NULL DEFAULT 1,
    update_reason TEXT,

    -- Outcome (filled by retro after horizon passes)
    actual_direction VARCHAR(10),
    actual_price_vnd BIGINT,
    outcome_date DATE,
    brier_score DECIMAL(6,4),
    direction_correct BOOLEAN,
    price_error_pct DECIMAL(8,2),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_beliefs_date_ticker
    ON agent_beliefs(record_date, ticker);
CREATE INDEX IF NOT EXISTS idx_beliefs_agent_date
    ON agent_beliefs(agent_key, record_date DESC);
CREATE INDEX IF NOT EXISTS idx_beliefs_chain
    ON agent_beliefs(prior_belief_id) WHERE prior_belief_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_beliefs_unresolved
    ON agent_beliefs(record_date) WHERE outcome_date IS NULL;

-- Rolling accuracy view for prompt injection
CREATE OR REPLACE VIEW v_agent_belief_accuracy AS
SELECT
    agent_key,
    ensemble_type,
    COUNT(*) FILTER (WHERE brier_score IS NOT NULL) AS scored_beliefs,
    ROUND(AVG(brier_score) FILTER (WHERE brier_score IS NOT NULL), 4) AS avg_brier,
    ROUND(AVG(brier_score) FILTER (WHERE brier_score IS NOT NULL
        AND record_date >= CURRENT_DATE - 30), 4) AS brier_30d,
    ROUND(AVG(CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END)
        FILTER (WHERE direction_correct IS NOT NULL), 3) AS direction_accuracy,
    ROUND(AVG(conviction), 3) AS avg_conviction,
    ROUND(AVG(days_held) FILTER (WHERE belief_status != 'NEW'), 1) AS avg_streak_length,
    COUNT(*) FILTER (WHERE belief_status = 'REVERSED') AS reversals,
    ROUND(AVG(CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END)
        FILTER (WHERE days_held >= 3 AND direction_correct IS NOT NULL), 3)
        AS accuracy_streak_3plus,
    ROUND(AVG(CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END)
        FILTER (WHERE days_held = 1 AND direction_correct IS NOT NULL), 3)
        AS accuracy_fresh_beliefs
FROM agent_beliefs
GROUP BY agent_key, ensemble_type;
