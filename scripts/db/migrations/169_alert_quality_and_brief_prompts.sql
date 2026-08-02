-- Migration 169: Alert quality + brief prompt improvements
-- Data-only (UPDATE agent_prompts) — no DDL, default DATABASE_URL works.

-- 1. Synthesis: Sector bias applies to swing entries only, not longterm holds
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## SECTOR BIAS vs LONGTERM HOLDINGS\nWhen SECTOR FOCUS flags a sector as "cold" or "avoid":\n- This applies ONLY to new SWING entries in that sector.\n- LONGTERM holdings in that sector are NOT affected by sector rotation bias.\n- If a LONGTERM holding''s sector is flagged cold, note: "Sector cold for swing, but LONGTERM thesis intact."\n- NEVER recommend EXIT/TRIM on a LONGTERM position solely because its sector is cold.'
WHERE agent_key = 'synthesis'
  AND system_prompt NOT LIKE '%SECTOR BIAS vs LONGTERM HOLDINGS%';

-- 2. Synthesis: EXIT recommendations must include walk-away price + time deadline
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## EXIT COMPLETENESS RULE\nEvery EXIT recommendation in MY HOLDINGS MUST include:\n1. PRIMARY EXIT: specific price level\n2. WALK-AWAY PRICE: fallback if primary doesn''t fill\n3. TIME DEADLINE: when to force-exit (e.g., "ATC market sell")\nFormat: "EXIT at Xk | Walk-away: Yk by 14:00 | Deadline: ATC market sell"'
WHERE agent_key = 'synthesis'
  AND system_prompt NOT LIKE '%EXIT COMPLETENESS RULE%';

-- 3. Alert registrar: Replace WATCH with HOLD in action list
UPDATE agent_prompts
SET system_prompt = REPLACE(system_prompt, 'BUY, TRIM, EXIT, ADD, WATCH', 'BUY, TRIM, EXIT, ADD, HOLD')
WHERE agent_key = 'alert_registrar'
  AND system_prompt LIKE '%BUY, TRIM, EXIT, ADD, WATCH%';

-- 4. Alert registrar: Add holdings-only rule for TRIM/EXIT/ADD
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## HOLDINGS-ONLY RULE FOR TRIM/EXIT/ADD\nTRIM, EXIT, and ADD alerts can ONLY be for tickers in CURRENT HOLDINGS.\nThe tool rejects TRIM/EXIT/ADD for non-held tickers automatically.'
WHERE agent_key = 'alert_registrar'
  AND system_prompt NOT LIKE '%HOLDINGS-ONLY RULE FOR TRIM/EXIT/ADD%';
