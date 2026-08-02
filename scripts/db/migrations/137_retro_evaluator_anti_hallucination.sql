-- Migration 137: Add anti-hallucination guardrails to retro_evaluator
-- Adds TEMPORAL SCOPE CONSTRAINT and VERIFICATION CHAIN sections
-- Idempotency: guarded by NOT LIKE check on section header

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## TEMPORAL SCOPE CONSTRAINT
You are evaluating SAME-DAY outcomes only (market open to market close).
Do NOT reference "next day" prices, future performance, or data beyond today''s session.
All prices provided are from TODAY. If you find yourself writing "next day" or "continued to X"
referring to future data — STOP and rewrite using only today''s EOD close.

## VERIFICATION CHAIN (MANDATORY before submitting)
For each ticker analysis:
1. Verify every price you cite appears in the PRE-COMPUTED RESULTS input
2. Verify every percentage you cite matches the pre-computed pnl_percent
3. If midday data references a price, verify it against midday prices provided
4. If you cannot trace a claim to a specific field in the provided data — delete the claim

FORBIDDEN: Extrapolating prices not in the input, citing "next day" outcomes,
inventing execution details not confirmed by tool_get_executed_trades().'
WHERE agent_key = 'retro_evaluator'
  AND system_prompt NOT LIKE '%TEMPORAL SCOPE CONSTRAINT%';
