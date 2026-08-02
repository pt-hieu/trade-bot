-- Migration 145: Change alert_registrar model from MiniMax-M2.5 to Kimi-K2.5
-- Reason: MiniMax-M2.5 bug — cannot override null for optional tool params
--         (stop_price, target_price), loops until request_limit=15 on every run

UPDATE agent_prompts
SET model_id = 'moonshotai/Kimi-K2.5',
    model_tier = 'mid'
WHERE agent_key = 'alert_registrar';
