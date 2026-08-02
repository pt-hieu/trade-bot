-- Migration 179: Set max_tokens for longterm and positions_technical agents.
-- Both had NULL max_tokens → Kimi-K2.5 default 2048 → truncation on tool-call turns.

UPDATE agent_prompts SET max_tokens = 8192
WHERE agent_key IN ('longterm', 'positions_technical')
  AND (max_tokens IS NULL OR max_tokens < 8192);
