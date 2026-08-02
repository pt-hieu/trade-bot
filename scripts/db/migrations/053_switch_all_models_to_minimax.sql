-- Migration 053: Switch all agents to MiniMax-M2.5
-- Replaces Kimi-K2.5 (heavy) and GLM-4.5-Air (light/critic) with MiniMax-M2.5

UPDATE agent_prompts SET model_id = 'MiniMaxAI/MiniMax-M2.5'
WHERE model_id IN ('moonshotai/Kimi-K2.5', 'zai-org/GLM-4.5-Air-FP8')
