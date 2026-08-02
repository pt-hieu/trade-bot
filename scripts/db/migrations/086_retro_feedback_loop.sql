-- Migration 086: Close the feedback loop — add tool_get_learnings to self-aware agents
-- Agents gain access to historical accuracy data for self-calibration

-- sector_rotation: check historical hot sector accuracy before scoring
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_learnings'),
    system_prompt = system_prompt || E'\n\n## Self-Calibration\nBefore scoring sectors, call tool_get_learnings(query="rotation_patterns") to check your historical accuracy.\n- If a sector''s hot accuracy < 40%: reduce conviction or skip.\n- If overall rotation accuracy < 50%: flag uncertainty in reasoning.',
    updated_at = NOW()
WHERE agent_key = 'sector_rotation';

-- market_level: check regime accuracy history before classifying
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_learnings'),
    system_prompt = system_prompt || E'\n\n## Self-Calibration\nBefore classifying regime, call tool_get_learnings(query="macro_patterns") to check regime accuracy history.\n- If your CAUTIOUS calls were wrong >50% of time: bias toward NEUTRAL.\n- If overall accuracy < 50%: lower regime_confidence by 10 points.',
    updated_at = NOW()
WHERE agent_key = 'market_level';

-- midday: check historical adjustment effectiveness before overriding
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_learnings'),
    system_prompt = system_prompt || E'\n\n## Adjustment History\nCall tool_get_learnings(query="midday_insights") before making recommendation overrides.\n- If historical adjustments were harmful > helpful: be conservative with overrides.\n- Reference: "Midday adjustments were helpful X% of the time."',
    updated_at = NOW()
WHERE agent_key = 'midday';

-- sector: check sector win rates before assigning conviction
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_learnings'),
    system_prompt = system_prompt || E'\n\n## Sector Performance Context\nCall tool_get_learnings(query="sector_bias") at the start of analysis.\n- Use sector win rates to calibrate conviction on BUY/AVOID signals.\n- If a sector has < 30% win rate recently: flag elevated risk.',
    updated_at = NOW()
WHERE agent_key = 'sector';
