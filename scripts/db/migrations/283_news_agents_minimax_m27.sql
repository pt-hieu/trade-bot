-- Migration 283: Switch news pipeline agents + fallback model to MiniMax M2.7
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Updates: news_examiner, sector_news, catalysts, capital_events
-- Also replaces any remaining MiniMaxAI/MiniMax-M2.5 references
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/283_news_agents_minimax_m27.sql

-- News pipeline agents → MiniMax M2.7
UPDATE agent_prompts
SET model_id = 'minimax/minimax-m2.7', updated_at = NOW()
WHERE agent_key IN ('news_examiner', 'sector_news', 'catalysts', 'capital_events');

-- Replace any remaining MiniMax M2.5 references across all agents
UPDATE agent_prompts
SET model_id = 'minimax/minimax-m2.7', updated_at = NOW()
WHERE model_id = 'MiniMaxAI/MiniMax-M2.5';
