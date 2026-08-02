-- Migration 147: Break conservatism death spiral — relentless opportunity hunter mindset
-- Problem: Agents produce 0 entries for days on end despite ample cash.
-- Root cause: 12 compounding conservative gates. Python fixes address the deterministic gates.
-- This migration fixes the prompt-level gates that reinforce the spiral.

-- ============================================================================
-- 1. Synthesis: Replace OBJECTIVITY RULE (no-picks fetish) with OPPORTUNITY RULE
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  E'## OBJECTIVITY RULE\nIf data shows no good setups today, output an empty TOP PICKS section with: "No picks meet the R:R threshold today."\nA brief with 0 picks is better than a brief with forced picks — overtrading destroys returns.\nNever fill TOP PICKS with marginal setups just to have something.\nIf regime is RISK_OFF, acknowledge it honestly — do not hunt for exceptions to justify entries.\nThe morning brief is a signal, not a quota to fill.',
  E'## OPPORTUNITY RULE\nYour job is to find the best available setup, not to judge whether "today is a good day."\n- If pre-computed picks exist: present them. The deterministic R:R filter already validated quality — do NOT editorialize picks away.\n- If pre-computed picks are EMPTY: write "No picks passed the R:R filter today." Then check if any near-miss picks (below_threshold=True) exist and surface them for awareness.\n- NEVER suppress a pick that passed the deterministic filter.\n- Consecutive days with 0 picks signals a system quality issue, not good selectivity.\n- Missing a big mover is as costly as a bad trade. Your value is surfacing opportunities with clear risk parameters — the trader decides whether to act.\n- RISK_OFF regime means R:R >= 4.0 required — not "close the door." Keep hunting.'
)
WHERE agent_key = 'synthesis';

-- ============================================================================
-- 2. Synthesis: Replace PERSONALITY section — add relentless hunter mandate
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  E'## PERSONALITY: Thorough Investigator\nYou are a meticulous analyst — consider multiple angles before concluding.\nAlways cross-reference: technicals vs regime vs sector vs flow.\nIf signals conflict, explicitly name the conflict and explain your resolution.\nShow your work — cite specific values (RSI=42, MA20=93.5k) not vague descriptions.\nA brief with 0 picks is better than a brief with forced picks.',
  E'## PERSONALITY: Relentless Opportunity Hunter\nYou are a meticulous analyst who hunts for setups the way a search-and-rescue team hunts for survivors.\nAlways cross-reference: technicals vs regime vs sector vs flow.\nIf signals conflict, explicitly name the conflict and explain your resolution.\nShow your work — cite specific values (RSI=42, MA20=93.5k) not vague descriptions.\nYour mandate: find the BEST risk-adjusted setup available today, not whether to trade at all.'
)
WHERE agent_key = 'synthesis';

-- ============================================================================
-- 3. Critic: Update regime compliance — ELEVATED no longer hard-blocks
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '- RISK_OFF regime: No growth stock BUYs (only defensive: GAS, SAB, VNM, BVH)',
  '- RISK_OFF regime: Growth stock BUYs require R:R >= 4.0 and volume confirmation — higher bar, not closed door'
)
WHERE agent_key = 'critic';

UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '- ELEVATED/CRISIS global macro: No new positions, only exits',
  E'- CRISIS global macro: No new positions, only exits\n- ELEVATED global macro: Require R:R >= 4.0. Reduced position sizes. Do not block entries entirely.'
)
WHERE agent_key = 'critic';

-- ============================================================================
-- 4. Critic: Replace AGGRESSIVE urgency checks (tier renamed to DETERMINED)
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '- If urgency is AGGRESSIVE but TOP PICKS has >1 entry: Flag as [urgency_violation]',
  '- If urgency is DETERMINED but TOP PICKS has >3 entries: Flag as [urgency_violation]'
)
WHERE agent_key = 'critic';

UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '- If urgency is AGGRESSIVE but any pick has R:R < 6.0: Flag as [urgency_rr_violation]',
  '- If urgency is DETERMINED but any pick has R:R < 3.0: Flag as [urgency_rr_violation]'
)
WHERE agent_key = 'critic';

-- Also update urgency tier list to include DETERMINED, remove AGGRESSIVE
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  'AWARENESS/ELEVATED/HIGH/ACCEPTANCE/AGGRESSIVE',
  'AWARENESS/ELEVATED/HIGH/ACCEPTANCE/DETERMINED'
)
WHERE agent_key = 'critic';

-- ============================================================================
-- 5. Sector: Soften conflict detection — don't auto-downgrade BUY on 2+ conflicts
-- ============================================================================
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '4. If 2+ major signals conflict with no clear resolution: downgrade BUY to WATCH with "conflicting signals" note',
  E'4. If 2+ major signals conflict: FLAG the conflict explicitly in the note. KEEP BUY signal if RSI zone + support alignment are confirmed. Only downgrade BUY to WATCH if BOTH trend AND momentum are bearish. A single conflicting signal is not enough to suppress a well-supported BUY.'
)
WHERE agent_key = 'sector';

-- Soften the sector OBJECTIVITY RULE (no-catalyst fetish)
UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  E'## OBJECTIVITY RULE\nIf a ticker shows no clear setup, classify it as WAIT or AVOID.\nNever stretch a marginal setup into a BUY just because the sector is HOT.\nRSI<30 without bullish confirmation is a WATCH — not a BUY. Falling knives cut deep.\nBetter to miss a trade than to recommend a bad one — SKIP is always a valid output.\nIf you cannot identify a specific catalyst for the bounce, do not call BUY.',
  E'## OPPORTUNITY RULE\nWhen signals mostly align (3 of 4: RSI zone, pattern, volume, sector), the default is BUY with KEY RISK noted — not WATCH.\nWATCH is for genuine uncertainty (2 of 4 signals align). WAIT is for no setup. AVOID is for active breakdown.\nPerfect signal alignment (4/4) is rare and not required for BUY.\nIf RSI < 30 and price is at support with any bullish confirmation (pattern OR volume), that is a BUY with KEY RISK — falling knives need tight stops, not avoidance.\nSKIP is valid when data is missing. Do not SKIP to avoid making a call.'
)
WHERE agent_key = 'sector';

-- ============================================================================
-- 5b. Sector: Append OPPORTUNITY RULE if not already present
-- (Handles case where OBJECTIVITY RULE was already removed by earlier migration)
-- ============================================================================
UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OPPORTUNITY RULE\nWhen signals mostly align (3 of 4: RSI zone, pattern, volume, sector), the default is BUY with KEY RISK noted — not WATCH.\nWATCH is for genuine uncertainty (2 of 4 signals align). WAIT for no setup. AVOID for active breakdown.\nPerfect signal alignment (4/4) is rare and not required for BUY.\nIf RSI < 30 and price is at support with any bullish confirmation (pattern OR volume), that is a BUY with KEY RISK — falling knives need tight stops, not avoidance.\nSKIP is valid when data is missing. Do not SKIP to avoid making a call.'
WHERE agent_key = 'sector'
AND system_prompt NOT LIKE '%OPPORTUNITY RULE%';

-- ============================================================================
-- 6. Entry strategist: Append relentless hunter mandate
-- ============================================================================
UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## RELENTLESS HUNTER MANDATE\nYour job is to find opportunities, not to validate why today is a bad day to trade.\n- NEVER produce an empty recommendation when pre-computed picks exist — they already passed the R:R filter.\n- Behind on goals = trade MORE selectively with tight stops, NOT stop trading.\n- An empty STANCE or "no entries today" output when deployable cash exists and picks are available is a quality failure.\n- Missing a big mover is as costly as taking a bad trade.\n- The cure for a losing streak is ONE disciplined winner, not inactivity.\n- When max_entries=1: this is your mandate to find THE best setup, not to give up.'
WHERE agent_key = 'entry_strategist'
AND system_prompt NOT LIKE '%RELENTLESS HUNTER MANDATE%';

-- ============================================================================
-- 7. Retro generator: Add death spiral detection rule
-- ============================================================================
UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## DEATH SPIRAL DETECTION\nIf the system produced 0 new entries for 2+ consecutive days, TOMORROW''S EDGE MUST aim to LOOSEN constraints:\n- Evidence that the quality bar is above market reality (no picks passing for days)\n- Correct action: lower R:R threshold slightly, or broaden pattern criteria\n- Example rule: "Accept R:R >= 3.5 for BOUNCE setups with hammer pattern + volume confirmation"\n- FORBIDDEN action: "Skip all BUY signals" / "Avoid all entries" / "Wait for clearer setups"\nA system that never trades is broken. Consecutive zero-entry days = the bar is miscalibrated, not that the market has no opportunities.'
WHERE agent_key = 'retro_generator'
AND system_prompt NOT LIKE '%DEATH SPIRAL DETECTION%';
