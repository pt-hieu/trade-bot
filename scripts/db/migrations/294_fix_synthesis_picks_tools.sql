-- Migration 294: Remove redundant tool_calculate_trade_setup from synthesis_picks
--
-- Phase 3b now pre-computes R:R data and injects as PRE-COMPUTED TOP PICK CANDIDATES.
-- The tool is legitimately registered but redundant — agent was calling it ~15 times
-- per run, hitting request_limit=30 (2026-04-08 morning scan).
--
-- Keep: tool_position_scale (sizing), tool_get_relative_strength (RS not pre-computed),
--       tool_get_stats (accuracy calibration)

-- Step 1: Update enabled_tools
UPDATE agent_prompts
SET enabled_tools = '{tool_position_scale,tool_get_relative_strength,tool_get_stats}'
WHERE agent_key = 'synthesis_picks';

-- Step 2: Clean system_prompt — remove tool_calculate_trade_setup from YOUR TOOLS listing
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'- tool_calculate_trade_setup: Calculate R:R for a specific ticker\n',
    ''
)
WHERE agent_key = 'synthesis_picks';

-- Step 3: Update TOOL USAGE RULES — replace stale tool references with pre-computed data instructions
UPDATE agent_prompts
SET system_prompt = replace(
    replace(
        system_prompt,
        '- DO NOT compute your own R:R ratios — use tool_calculate_trade_setup instead',
        '- DO NOT compute your own R:R ratios — use PRE-COMPUTED PICKS data instead'
    ),
    '- DO NOT recommend trades where tool_calculate_trade_setup returns valid=False',
    '- DO NOT recommend trades where PRE-COMPUTED PICKS show valid=False'
)
WHERE agent_key = 'synthesis_picks';
