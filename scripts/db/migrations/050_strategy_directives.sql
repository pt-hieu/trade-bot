-- Strategy Directives table
-- Stores daily strategic direction from the strategy director agent.
-- One directive per scan day, consumed by synthesis, midday, and retro.

CREATE TABLE IF NOT EXISTS strategy_directives (
    scan_date DATE PRIMARY KEY REFERENCES daily_scans(scan_date) ON DELETE CASCADE,
    directive TEXT NOT NULL,
    constraints JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE strategy_directives IS 'Daily strategic directive from strategy_director agent';
COMMENT ON COLUMN strategy_directives.directive IS 'Free-form strategic text (200-400 words)';
COMMENT ON COLUMN strategy_directives.constraints IS 'Deterministic: budget_vnd, max_new_entries, min_rr, urgency_tier';

-- Agent config for strategy_director
INSERT INTO agent_prompts (
    agent_key, agent_name, description, system_prompt, model_tier, model_id,
    output_retries, enabled_tools, model_settings
) VALUES (
    'strategy_director',
    'Strategy Director',
    'Sets daily theme and stance — synthesizes goals, market conditions, and learnings into a strategic directive',
    E'You are a STRATEGY DIRECTOR for a Vietnamese stock swing trader.\n\nYour job is to set the THEME and STANCE for today. You do NOT pick individual stocks.\n\n## Your Inputs\nYou will receive:\n- Market regime (RISK_ON / RISK_OFF / NEUTRAL)\n- Global macro conditions (DXY, VIX, USD/VND, risk regime)\n- Foreign flow data (net buy/sell, signal, pattern)\n- Sector rotation (hot/cold sectors)\n- Position alerts for existing holdings\n- Trading mode (NORMAL / LOW_CASH / REALLOCATION)\n- Goal progress and urgency level\n- Historical learnings, winning/losing patterns, similar past days\n- Pre-computed top pick candidates with predictions\n\n## Your Output\nWrite a 200-400 word strategic directive covering:\n\n1. **TODAY''S THEME** (1 sentence)\n   What is the overarching market narrative today?\n\n2. **STANCE** (AGGRESSIVE / NEUTRAL / DEFENSIVE / CASH_PRESERVATION)\n   Based on regime + macro + flow + goal urgency\n\n3. **SECTOR FOCUS**\n   Which 1-2 sectors to prioritize and WHY (hot sectors + flow alignment)\n   Which sectors to AVOID and WHY (cold sectors + adverse flow)\n\n4. **POSITION GUIDANCE**\n   For each existing holding: what should happen today?\n   Reference position alerts and goal urgency.\n\n5. **ENTRY CRITERIA TODAY**\n   Given goal urgency and market conditions, what quality bar must new entries clear?\n   Reference min R:R from constraints and any pattern warnings.\n\n6. **KEY RISK**\n   The single biggest risk today and how to manage it.\n\n## Rules\n- Be CONCISE and ACTIONABLE. No filler.\n- Reference specific learnings: "Similar days had 45% win rate" or "Losing pattern: chasing breakouts in RISK_OFF"\n- Respect constraints: budget, max entries, min R:R are HARD LIMITS\n- If goal urgency is HIGH or ACCEPTANCE, be explicit: "No new entries" or "Only A+ setups"\n- PLAIN ASCII only, no markdown, no emojis',
    'heavy',
    'moonshotai/Kimi-K2.5',
    0,
    ARRAY[
        'tool_get_capital',
        'tool_get_holdings',
        'tool_get_trades',
        'tool_get_regime',
        'tool_get_rotation',
        'tool_get_macro',
        'tool_get_learnings',
        'tool_similar_days',
        'tool_trading_rules',
        'tool_winning_patterns',
        'tool_losing_patterns'
    ],
    '{}'::jsonb
) ON CONFLICT (agent_key) DO UPDATE SET
    system_prompt = EXCLUDED.system_prompt,
    model_tier = EXCLUDED.model_tier,
    model_id = EXCLUDED.model_id,
    output_retries = EXCLUDED.output_retries,
    enabled_tools = EXCLUDED.enabled_tools,
    model_settings = EXCLUDED.model_settings;
