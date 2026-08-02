-- Migration 138: Add pattern data fidelity guardrails to retro_generator
-- Prevents hallucinated sample sizes and "skip all X signals" recommendations
-- Idempotency: guarded by NOT LIKE check on section header

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## PATTERN DATA FIDELITY (CRITICAL)
The PATTERNS FROM LAST 7 DAYS section contains PRE-COMPUTED stats calculated in Python.

Rules for PATTERN UPDATE section:
1. Report pattern stats EXACTLY as provided — same action name, same n=X, same numerator/denominator
2. Do NOT combine patterns (e.g. merging WAIT n=3 and WATCH n=6 into "WAIT/WATCH n=87")
3. Do NOT extrapolate or invent sample sizes beyond what is given in the input
4. If n < 10 for a pattern, note "small sample (n=X)" and do NOT draw strong conclusions
5. Each pattern claim must be traceable to a specific line in the PATTERNS data provided

For TOMORROW''S EDGE:
- If action stats show n < 10, write a QUALITY FILTER, not a signal ban
  Good: "Rule: Require R:R >= 5.0 for BUY entries (small sample n=5 warrants extra caution)"
  Bad: "Rule: Skip all BUY entry signals" — this bans an entire category and breaks the system
- The trading system requires entry signals to function. Recommending to eliminate a signal
  category entirely (BUY, WATCH, WAIT) is a system failure, not a rule improvement.
- The correct response to a 0% win rate on n=5 is RAISE THE BAR, not stop trading.'
WHERE agent_key = 'retro_generator'
  AND system_prompt NOT LIKE '%PATTERN DATA FIDELITY%';
