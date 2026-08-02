-- Migration 198: LLM config optimization — right-size max_tokens + model differentiation
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- 4a: Right-size max_tokens per agent role to avoid over-spending context budget
-- 4b: Lighter model for simple interpreter agents (macro_interpreter, narrative_labeler)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/198_llm_config_optimization.sql

-- Interpreters — simple extraction, 1000 tokens
UPDATE agent_prompts SET max_tokens = 1000, updated_at = NOW()
WHERE agent_key IN ('macro_interpreter', 'narrative_labeler')
  AND max_tokens != 1000;

-- Sub-analysts — structured per-sector report, 3000 tokens
UPDATE agent_prompts SET max_tokens = 3000, updated_at = NOW()
WHERE agent_key IN ('sector_technical', 'sector_news', 'sector_enrichment',
                     'positions_technical', 'positions_value', 'positions_thesis',
                     'retro_parser', 'market_level', 'sector_rotation')
  AND max_tokens != 3000;

-- Aggregators + retro evaluators — 5000 tokens
UPDATE agent_prompts SET max_tokens = 5000, updated_at = NOW()
WHERE agent_key IN ('sector_aggregator', 'positions_aggregator',
                     'retro_evaluator', 'retro_commentary')
  AND max_tokens != 5000;

-- General pipeline agents — 5000 tokens
UPDATE agent_prompts SET max_tokens = 5000, updated_at = NOW()
WHERE agent_key IN ('midday', 'alert_analyst', 'alert_registrar',
                     'catalysts', 'capital_events', 'news_examiner',
                     'longterm', 'longterm_review', 'positions',
                     'trading_mode', 'watchlist_coordinator',
                     'watchlist_sector_evaluator',
                     'positions_pev_alert', 'positions_pev_verifier')
  AND max_tokens != 5000;

-- Strategy agents — 8000 tokens
UPDATE agent_prompts SET max_tokens = 8000, updated_at = NOW()
WHERE agent_key IN ('entry_strategist', 'position_strategist')
  AND max_tokens != 8000;

-- Writers — full brief sections, 10000 tokens
UPDATE agent_prompts SET max_tokens = 10000, updated_at = NOW()
WHERE agent_key IN ('synthesis_holdings', 'synthesis_picks', 'retro_generator')
  AND max_tokens != 10000;

-- Refiner — rewrites full brief, 12000 tokens
UPDATE agent_prompts SET max_tokens = 12000, updated_at = NOW()
WHERE agent_key = 'refiner'
  AND max_tokens != 12000;

-- Critic stays at 20000 (already set by migration 193)

-- 4b: Model differentiation — interpreters use lighter model
UPDATE agent_prompts SET model_id = 'zai-org/GLM-4.5-Air-FP8', updated_at = NOW()
WHERE agent_key IN ('macro_interpreter', 'narrative_labeler')
  AND model_id != 'zai-org/GLM-4.5-Air-FP8';
