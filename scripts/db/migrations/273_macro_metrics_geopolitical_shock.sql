-- Add resolved geopolitical shock data to macro_metrics.
-- Python pipeline resolves phases once. Web reads the result.
-- Eliminates Python/TS phase resolution divergence.

ALTER TABLE macro_metrics
ADD COLUMN IF NOT EXISTS geopolitical_shock JSONB;

COMMENT ON COLUMN macro_metrics.geopolitical_shock
IS 'Pipeline-resolved geopolitical shock dict: {phase_name, catalyst_event, behavior, impact, affected_tickers, notes, catalyst_key, days_active, phase_stale}';

-- Fix Hormuz crisis phase period: "Apr 2026+" -> "Apr 1, 2026+" (missing day caused silent parse failure)
UPDATE catalysts
SET phases = jsonb_set(phases, '{resolution_or_escalation,period}', '"Apr 1, 2026+"')
WHERE catalyst_key = 'hormuz_closure_2026'
  AND phases->'resolution_or_escalation'->>'period' = 'Apr 2026+';
