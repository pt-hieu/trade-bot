-- Migration 024: Add goal urgency rules to agent prompts
-- Appends new sections to synthesis, critic, refiner, midday, and retro_generator prompts

-- 1. Synthesis: Add goal urgency tiers after Capital Awareness section
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CRITICAL: Goal Urgency\nAfter calling tool_get_capital(), assess urgency from goal data:\n\n| Condition | Level | TOP PICKS Rule |\n|-----------|-------|----------------|\n| On track or ahead | NORMAL | Standard R:R >= 3.0 |\n| Behind + >15 days | AWARENESS | Note "behind schedule" in GOAL PROGRESS |\n| Behind + 10-15 days | ELEVATED | Only R:R >= 4.0, max 3 picks |\n| Behind + 5-10 days | HIGH | Only R:R >= 5.0, max 1-2 picks, must match winning pattern |\n| Behind + <5 days | ACCEPTANCE | No new entries, manage existing positions |\n\nIn GOAL PROGRESS section, ALWAYS include:\n- Urgency level (NORMAL/AWARENESS/ELEVATED/HIGH/ACCEPTANCE)\n- If ELEVATED or higher: "URGENCY: Need X VND/day - only highest-conviction setups"\n- If ACCEPTANCE: "GOAL AT RISK - focus on capital preservation, do not chase"\n\nGoal urgency MUST influence TOP PICKS selection:\n- ELEVATED: Only include picks with R:R >= 4.0 and matching winning patterns\n- HIGH: Max 1-2 picks, must match winning pattern with >60% hit rate\n- ACCEPTANCE: No new entries, focus on managing existing positions for best exit prices',
    updated_at = NOW()
WHERE agent_key = 'synthesis' AND is_active = TRUE;

-- 2. Critic: Add urgency compliance check
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n### 11. Goal Urgency Compliance (MAJOR)\nCheck GOAL PROGRESS section:\n- If goal is behind schedule with <15 days left, brief MUST show urgency level (AWARENESS/ELEVATED/HIGH/ACCEPTANCE)\n- If urgency is HIGH but TOP PICKS has >2 entries: Flag as [urgency_violation]\n- If urgency is ACCEPTANCE but TOP PICKS has any BUY: Flag as [urgency_violation]\n- If urgency is ELEVATED but any pick has R:R < 4.0: Flag as [urgency_rr_violation]\n- If GOAL PROGRESS section is missing urgency level when behind schedule: Flag as [missing_urgency]',
    updated_at = NOW()
WHERE agent_key = 'critic' AND is_active = TRUE;

-- 3. Refiner: Add output-only constraint to prevent leaked reasoning
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## OUTPUT RULES (CRITICAL)\n- Return ONLY the refined brief text\n- Start directly with the first section header (GOAL PROGRESS or CONTEXT)\n- Do NOT include thinking, verification steps, or calculations before the brief\n- Do NOT prefix output with "Now let me...", "Let me verify...", "Holdings verified...", "REFINED MORNING BRIEF", or any preamble\n- The very first line of your output must be a section header like "GOAL PROGRESS" or "CONTEXT"',
    updated_at = NOW()
WHERE agent_key = 'refiner' AND is_active = TRUE;

-- 4. Midday: Add goal progress instruction
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## Goal Awareness\nYou now have access to tool_get_goal() which returns trading goal progress.\nAfter reviewing positions and cash, call tool_get_goal() to check progress.\nIf behind schedule, note whether today''s session helped or hurt progress.\nInclude a brief GOAL STATUS line in your capital_note output.',
    updated_at = NOW()
WHERE agent_key = 'midday' AND is_active = TRUE;

-- 5. Retro Generator: Add goal tracking section
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\nGOAL TRACKING (include if goal data is provided)\n- Daily target needed: X VND/day\n- Today''s realized P/L from closed trades: Y VND (or "no trades closed")\n- Assessment: On track / Falling behind / Critical\n- If behind: What needs to change tomorrow to get back on track',
    updated_at = NOW()
WHERE agent_key = 'retro_generator' AND is_active = TRUE;
