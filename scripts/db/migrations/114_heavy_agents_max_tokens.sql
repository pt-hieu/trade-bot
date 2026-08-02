-- Migration 114: Set max_tokens = 20000 for all heavy tier agents
--
-- Heavy agents with max_tokens = null use Together AI's default (2048),
-- causing finish_reason: length truncation on complex structured outputs.
-- Kimi-K2.5 hit this twice during retro evaluation (2x retries observed).

UPDATE agent_prompts
SET max_tokens = 20000
WHERE model_tier = 'heavy';
