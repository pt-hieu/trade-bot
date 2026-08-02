-- Switch all MiniMax-M2.5 agents to Kimi-K2.5
-- MiniMax had 503 failures and validation exhaustion issues on 2026-03-06
UPDATE agent_prompts
SET model_id = 'moonshotai/Kimi-K2.5'
WHERE model_id = 'MiniMaxAI/MiniMax-M2.5';
