-- Migration 057: Morning brief quality fixes round 2
-- Fixes: trailing stop threading to director, no-invention rule for synthesis, invented picks check for critic

-- 1. Strategy Director: Add trailing stops mandate for POSITION GUIDANCE
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n- POSITION GUIDANCE STOPS: When PRE-COMPUTED TRAILING STOPS are provided, use them EXACTLY.\n  - LONGTERM holdings: Write thesis-based exit criteria + catastrophic floor level from pre-computed data.\n  - SWING holdings: Use the exact stop level from pre-computed data.\n  - NEVER use breakeven_stop from tool_get_holdings() when pre-computed stops are available.\n- If goal achievability is UNREACHABLE, reflect this in STANCE (no desperate entries).'
WHERE agent_key = 'strategy_director';

-- 2. Synthesis: Add TOP PICKS RULES (no invention, near-miss handling)
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    '- Do NOT re-call tool_calculate_trade_setup for pre-computed picks',
    E'- Do NOT re-call tool_calculate_trade_setup for pre-computed picks\n\n## TOP PICKS RULES (CRITICAL)\n- If pre_computed_picks is provided: Use ONLY those picks with their entry/stop/target.\n- If pre_computed_picks is EMPTY: Write "No picks meet the R:R threshold today."\n  Do NOT invent picks from sector signal notes or broker price targets.\n- Picks with below_threshold=True are NEAR-MISS: Label as "NEAR-MISS (below X threshold)" and do NOT present as actionable.\n- Sector BUY signals provide context — they are NOT validated picks.'
)
WHERE agent_key = 'synthesis';

-- 3. Critic: Add invented picks detection check
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n### 13. Invented Picks Detection (CRITICAL)\nIf pre-computed picks were EMPTY but TOP PICKS section contains BUY recommendations:\n- Flag as [invented_picks]: "TOP PICKS contains recommendations not from pre-computed picks."\n- Severity: critical — LLM must not invent picks from sector notes or broker targets.\n- Near-miss picks (marked with below_threshold) should be labeled, not presented as actionable.'
WHERE agent_key = 'critic';
