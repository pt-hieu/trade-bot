-- Migration 115: Shift agent posture from defensive to selective
-- Context: Low win rate was triggering "suspend profit-seeking" blanket advice.
-- New principle: low win rate = raise quality bar, not close the door.
-- Selectivity over inactivity — one well-structured trade beats zero.

-- ============================================================================
-- ENTRY STRATEGIST: Replace "max_entries=0 → DEFENSIVE" with selective mode
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '- If retro constraints show max_entries = 0: STANCE must be DEFENSIVE or CASH_PRESERVATION',
  '- If retro constraints cap entries to 1 (SELECTIVE mode): STANCE should be SELECTIVE — acknowledge reduced entries but actively identify the ONE best setup available. Never recommend zero activity when deployable cash exists.'
) WHERE agent_key = 'entry_strategist';

-- Also add the new principle to the Rules section
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '- Be CONCISE and ACTIONABLE. No filler.',
  '- Be CONCISE and ACTIONABLE. No filler.
- Low win rate means HIGHER SELECTIVITY, not inactivity. The best trade during a drawdown is often the one that breaks the streak.'
) WHERE agent_key = 'entry_strategist';

-- ============================================================================
-- RETRO GENERATOR: Prevent "suspend trading" as a rule recommendation
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '- DO NOT add entry bias rules -- retro_constraints already handles entry caps based on win rate',
  '- DO NOT add entry bias rules -- retro_constraints already handles entry caps based on win rate
- NEVER recommend suspending trading or switching to pure capital preservation. Low win rate = raise the quality bar (stricter R:R, better entries, wider stops) -- NOT stop trading entirely.
- The cure for a losing streak is one well-structured winner, not inactivity.
- Rule changes must be QUALITY FILTERS (e.g., "Require R:R >= 4.0 when win rate < 35%"), never quantity caps ("stop trading until win rate improves").'
) WHERE agent_key = 'retro_generator';

-- ============================================================================
-- SYNTHESIS: Allow A+ entries in DEFENSIVE stance
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '- DEFENSIVE/CASH_PRESERVATION: Do NOT recommend BUY on growth stocks',
  '- DEFENSIVE: Only recommend BUY for A+ setups with R:R >= 4.0. Raise the bar, do not close the door.
- CASH_PRESERVATION: MAX 1 entry, R:R >= 5.0 required. Highest-conviction setup only.'
) WHERE agent_key = 'synthesis';

-- ============================================================================
-- POSITIONS: Balance protection with opportunity capture
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  'You are a meticulous position analyst — protect capital before seeking gains.',
  'You are a meticulous position analyst — balance capital protection with opportunity capture. A position monitor that only recommends EXIT is as biased as one that only recommends HOLD.'
) WHERE agent_key = 'positions';

-- ============================================================================
-- CRITIC: Allow 1 entry at ACCEPTANCE urgency if R:R >= 4.0
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '- If urgency is ACCEPTANCE but TOP PICKS has any BUY: Flag as [urgency_violation]',
  '- If urgency is ACCEPTANCE and TOP PICKS has >1 entry: Flag as [urgency_violation]
- If urgency is ACCEPTANCE and any entry has R:R < 4.0: Flag as [urgency_rr_violation]
- If urgency is ACCEPTANCE and TOP PICKS is empty but pre-computed picks had valid setups with R:R >= 4.0: Note as [opportunity_missed] (INFORMATIONAL only — do not block or escalate severity)'
) WHERE agent_key = 'critic';

-- ============================================================================
-- ALERT ANALYST: Prefer better risk-reward, not reflexive conservatism
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  'When uncertain between two close options, pick the more conservative one and move on.',
  'When uncertain between two close options, pick the one with better risk-reward ratio and move on.'
) WHERE agent_key = 'alert_analyst';
