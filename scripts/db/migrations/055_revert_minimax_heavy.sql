-- Migration 055: Revert heavy-tier agents from MiniMax-M2.5 to Kimi K2.5
--
-- MiniMax-M2.5 caused:
-- 1. 400 Input validation errors on context-heavy director prompts
-- 2. Hallucinated portfolio holdings in refiner output
-- 3. Missing directive sections in final brief
--
-- Critic + Light tiers stay on MiniMax-M2.5 (no issues observed).

UPDATE agent_prompts
SET model_id = 'moonshotai/Kimi-K2.5'
WHERE model_tier = 'heavy';
