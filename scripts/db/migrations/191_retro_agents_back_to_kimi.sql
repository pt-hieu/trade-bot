-- Revert retro agents back to Kimi-K2.5 (migration 190 set them to MiniMax).
-- Kimi timeout issues handled by 180s httpx timeout + fallback to MiniMax in code.

UPDATE agent_prompts
SET model_id = 'moonshotai/Kimi-K2.5'
WHERE agent_key IN ('retro_commentary', 'retro_generator')
  AND model_id = 'MiniMaxAI/MiniMax-M2.5';
