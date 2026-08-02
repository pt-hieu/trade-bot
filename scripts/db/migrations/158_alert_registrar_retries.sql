-- Migration 158: Bump alert_registrar output_retries from 0 to 3
-- Kimi-K2.5 sometimes returns empty responses. Only 1 retry is insufficient.

UPDATE agent_prompts
SET output_retries = 3
WHERE agent_key = 'alert_registrar'
  AND (output_retries IS NULL OR output_retries < 3);
