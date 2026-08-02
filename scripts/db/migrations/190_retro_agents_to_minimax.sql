-- Migrate retro_commentary and retro_generator from Kimi-K2.5 to MiniMax-M2.5.
-- Kimi-K2.5 has persistent timeout issues (30-180s+ for large retro prompts)
-- causing retro pipeline failures. MiniMax is faster and more reliable.

UPDATE agent_prompts
SET model_id = 'MiniMaxAI/MiniMax-M2.5'
WHERE agent_key IN ('retro_commentary', 'retro_generator')
  AND model_id = 'moonshotai/Kimi-K2.5';
