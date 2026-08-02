-- Migration 290: Kill LLM alert registrar
-- Deterministic alerts only — LLM registrar had 0% trigger rate (65% of volume, 0 conversions).
-- WATCH alerts are pure noise.

-- Deprecate LLM alert registrar agent
UPDATE agent_prompts SET is_active = false
WHERE agent_name = 'alert_registrar';

-- Cancel any remaining WATCH/HOLD alerts (noise)
UPDATE alerts SET status = 'cancelled', updated_at = NOW()
WHERE status = 'active' AND recommended_action IN ('WATCH', 'HOLD');
