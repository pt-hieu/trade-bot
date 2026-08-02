-- Migration 083: Add agent configs for alert_analyst and macro_interpreter
-- alert_analyst: hybrid agent (inline tools) migrated from hardcoded SYSTEM_PROMPT
-- macro_interpreter: lightweight PydanticAI agent replacing call_llm() in macro.py

INSERT INTO agent_prompts (agent_key, agent_name, system_prompt, model_tier, model_id, output_retries, enabled_tools, is_active)
VALUES (
    'alert_analyst',
    'Alert Analyst',
    'You are a quick-decision trading analyst for Vietnamese stocks.

An alert has triggered — analyze whether to act NOW or wait.

You have access to:
- Current technicals (RSI, MACD, trend)
- Portfolio holdings and cash balance
- The original alert rationale

Rules:
- Position size: max the configured max risk (200,000 VND default) per trade
- R:R >= 3.0 required for BUY_NOW
- If cash < 5M VND deployable, only recommend EXIT_NOW or WAIT
- Cash reserve: 10M VND minimum (never touch)
- Be decisive: BUY_NOW, WAIT, SKIP, or EXIT_NOW

Keep reasoning to 2-3 sentences. Be direct.',
    'critic',
    NULL,
    0,
    '{}',
    TRUE
)
ON CONFLICT (agent_key) DO UPDATE
    SET agent_name = EXCLUDED.agent_name,
        system_prompt = EXCLUDED.system_prompt,
        model_tier = EXCLUDED.model_tier,
        model_id = EXCLUDED.model_id,
        output_retries = EXCLUDED.output_retries,
        enabled_tools = EXCLUDED.enabled_tools,
        is_active = EXCLUDED.is_active,
        updated_at = NOW();

INSERT INTO agent_prompts (agent_key, agent_name, system_prompt, model_tier, model_id, output_retries, enabled_tools, is_active)
VALUES (
    'macro_interpreter',
    'Macro Interpreter',
    'You are a macro analyst. Write concise trading interpretation.',
    'light',
    NULL,
    0,
    '{}',
    TRUE
)
ON CONFLICT (agent_key) DO UPDATE
    SET agent_name = EXCLUDED.agent_name,
        system_prompt = EXCLUDED.system_prompt,
        model_tier = EXCLUDED.model_tier,
        model_id = EXCLUDED.model_id,
        output_retries = EXCLUDED.output_retries,
        enabled_tools = EXCLUDED.enabled_tools,
        is_active = EXCLUDED.is_active,
        updated_at = NOW();
