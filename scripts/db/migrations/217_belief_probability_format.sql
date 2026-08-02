-- Migration 217: Explicit probability format instructions for aggregator prompts
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Root cause: Aggregator LLMs output probabilities as percentages (45/35/20)
-- instead of decimals (0.45/0.35/0.20). The Pydantic model_validator normalizer
-- sees sum=100 > 1.5 and silently falls back to base rates for ALL aggregator beliefs.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/217_belief_probability_format.sql

-- sector_aggregator: add explicit probability format instructions
UPDATE agent_prompts
SET system_prompt = system_prompt || '

## PROBABILITY FORMAT (CRITICAL)

All probabilities MUST be decimals between 0.0 and 1.0, NOT percentages.
- CORRECT: bull_probability=0.45, base_probability=0.35, bear_probability=0.20
- WRONG: bull_probability=45, base_probability=35, bear_probability=20
The three probabilities MUST sum to approximately 1.0.
'
WHERE agent_key = 'sector_aggregator' AND is_active = true
AND system_prompt NOT LIKE '%PROBABILITY FORMAT%';

-- positions_aggregator: same probability format instructions
UPDATE agent_prompts
SET system_prompt = system_prompt || '

## PROBABILITY FORMAT (CRITICAL)

All probabilities MUST be decimals between 0.0 and 1.0, NOT percentages.
- CORRECT: bull_probability=0.45, base_probability=0.35, bear_probability=0.20
- WRONG: bull_probability=45, base_probability=35, bear_probability=20
The three probabilities MUST sum to approximately 1.0.
'
WHERE agent_key = 'positions_aggregator' AND is_active = true
AND system_prompt NOT LIKE '%PROBABILITY FORMAT%';
