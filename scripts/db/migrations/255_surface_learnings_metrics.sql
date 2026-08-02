-- Surface unsurfaced learnings metrics: strategy insights table + dominant error column

-- 1. Strategy insights — per-strategy win rates from retro pipeline
CREATE TABLE IF NOT EXISTS strategy_insights (
    id SERIAL PRIMARY KEY,
    strategy TEXT NOT NULL,
    win_rate DECIMAL(5,4),
    sample_size INTEGER,
    scan_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(strategy, scan_date)
);

CREATE INDEX IF NOT EXISTS idx_strategy_insights_date ON strategy_insights(scan_date DESC);

-- 2. Dominant error type on losing patterns (ANALYSIS_ERROR, EXECUTION_ERROR, CALIBRATION_ERROR, VARIANCE)
ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS dominant_error TEXT;
