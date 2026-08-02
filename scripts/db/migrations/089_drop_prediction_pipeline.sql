-- Migration 089: Drop prediction pipeline
-- Removes daily_predictions table and predictor agent config.
-- The prediction pipeline (LightGBM + Quant + LLM) is no longer used.

-- Drop table
DROP TABLE IF EXISTS daily_predictions CASCADE;

-- Remove predictor agent config
DELETE FROM agent_prompts WHERE agent_key = 'predictor';

-- Clean prediction text from synthesis prompt
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    E'## PREDICTION SIGNALS (Experimental \u2014 ~40% Accuracy)\nPre-computed picks may include ML prediction data.\nTreat as supplementary signal, not primary driver.\n- High confidence (>70%) + 3/3 agree: mention as supporting signal\n- Low confidence or conflict: note uncertainty, defer to technicals\n\n',
    ''
)
WHERE agent_key = 'synthesis';

-- Clean prediction section from critic prompt
UPDATE agent_prompts
SET system_prompt = REGEXP_REPLACE(
    system_prompt,
    E'### 13\\. Prediction Handling \\(INFORMATIONAL\\).*?### 14\\.',
    E'### 13.',
    'sn'
)
WHERE agent_key = 'critic';

-- Renumber critic section 15 → 14
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    '### 14. Cross-Section Ticker Dedup',
    '### 14. Cross-Section Ticker Dedup'
)
WHERE agent_key = 'critic';

-- Clean prediction over-reliance section from refiner prompt
UPDATE agent_prompts
SET system_prompt = REGEXP_REPLACE(
    system_prompt,
    E'### Fixing Prediction Over-Reliance.*?## STRUCTURED OUTPUT',
    E'## STRUCTURED OUTPUT',
    'sn'
)
WHERE agent_key = 'refiner';
