-- Migration 284: Switch watchlist pipeline agents to MiniMax M2.7
-- Type: Data (agent_prompts update)
--
-- Fallback chain: resolve_model_with_fallback() detects primary == fallback,
-- inverts to (MiniMax M2.7 primary 60s, Kimi K2.5 fallback 300s)

UPDATE agent_prompts
SET model_id = 'minimax/minimax-m2.7', updated_at = NOW()
WHERE agent_key IN ('watchlist_sector_evaluator', 'watchlist_coordinator', 'watchlist_update');
