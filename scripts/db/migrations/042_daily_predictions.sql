-- Daily predictions table for ML/LLM/Quant prediction pipeline
-- Stores per-ticker, per-day predictions from 3 sources + combined output

CREATE TABLE IF NOT EXISTS daily_predictions (
    id SERIAL PRIMARY KEY,
    scan_date DATE REFERENCES daily_scans(scan_date),
    ticker VARCHAR(10) NOT NULL,
    prediction_date DATE NOT NULL,

    -- LightGBM predictions
    lgbm_direction VARCHAR(10),      -- UP / DOWN / FLAT
    lgbm_confidence FLOAT,           -- max probability
    lgbm_up_prob FLOAT,
    lgbm_down_prob FLOAT,
    lgbm_flat_prob FLOAT,

    -- LLM prediction agent
    llm_direction VARCHAR(10),
    llm_confidence FLOAT,
    llm_magnitude_pct FLOAT,
    llm_reasoning TEXT,
    llm_key_drivers JSONB,

    -- Quantitative signals
    quant_direction VARCHAR(10),
    quant_score FLOAT,               -- -1.0 to +1.0
    quant_signals JSONB,             -- individual signal breakdown

    -- Combined (meta-combiner output)
    final_direction VARCHAR(10),
    final_confidence FLOAT,
    source_agreement INT,            -- how many sources agree (1-3)
    combiner_weights JSONB,          -- weights used {lgbm, llm, quant}

    -- Outcome (populated by retrospective)
    actual_return_pct FLOAT,
    prediction_correct BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(ticker, prediction_date)
);

CREATE INDEX IF NOT EXISTS idx_predictions_date
    ON daily_predictions(prediction_date);
CREATE INDEX IF NOT EXISTS idx_predictions_ticker_date
    ON daily_predictions(ticker, prediction_date);
CREATE INDEX IF NOT EXISTS idx_predictions_correct
    ON daily_predictions(prediction_correct)
    WHERE prediction_correct IS NOT NULL;
