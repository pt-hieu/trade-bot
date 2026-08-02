-- Fix critic FallbackModel(MiniMax, MiniMax) bug: both primary and fallback
-- were the same model, so any MiniMax outage kills the sole review gate.
-- Swap critic to Kimi primary → MiniMax becomes actual fallback.
-- Also fix retro_eval_critic temperature=null (defaults to ~1.0, should be 0.2).

UPDATE agent_prompts
SET model_id = 'moonshotai/Kimi-K2.5'
WHERE agent_key = 'critic'
  AND is_active = true;

UPDATE agent_prompts
SET model_id = 'moonshotai/Kimi-K2.5',
    temperature = 0.2
WHERE agent_key = 'retro_eval_critic'
  AND is_active = true;
