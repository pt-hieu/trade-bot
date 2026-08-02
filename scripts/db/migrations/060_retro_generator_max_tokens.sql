-- Migration 060: Increase retro_generator max_tokens to 10000
-- Prevents truncated output from Kimi-K2.5 on verbose retrospectives

UPDATE agent_prompts SET max_tokens = 10000 WHERE agent_key = 'retro_generator';
