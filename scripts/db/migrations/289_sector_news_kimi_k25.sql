-- Migration 289: Revert sector_news and catalysts to Kimi-K2.5
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Root cause: MiniMax M2.7 can't reliably produce complex nested Pydantic
-- structured output (SectorAnalystReport with nested TickerBelief 12+ fields,
-- CatalystDiscovery with 3 nested model types). Triggers PydanticAI retry
-- storms via inverted FallbackModel, exhausting request_limit=30.
--
-- Keep news_examiner + capital_events on MiniMax (simple flat schemas).
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/289_sector_news_kimi_k25.sql

UPDATE agent_prompts
SET model_id = 'moonshotai/Kimi-K2.5', updated_at = NOW()
WHERE agent_key IN ('sector_news', 'catalysts');
