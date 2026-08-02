-- Migration 103: Company research table + longterm watchlist automation columns

-- 1. company_research table

CREATE TABLE IF NOT EXISTS company_research (
    ticker         TEXT PRIMARY KEY,
    sections       JSONB NOT NULL DEFAULT '{}',
    research_date  DATE NOT NULL,
    auto_generated BOOLEAN NOT NULL DEFAULT TRUE,
    version        INTEGER NOT NULL DEFAULT 1,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. New columns on longterm_watchlist

ALTER TABLE longterm_watchlist
    ADD COLUMN IF NOT EXISTS entry_zone_method  TEXT DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS conviction_score   INTEGER,
    ADD COLUMN IF NOT EXISTS conviction_method  TEXT DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS review_flags       TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS last_reviewed_at   TIMESTAMPTZ;

-- 3. Update daily longterm agent tools

UPDATE agent_prompts
SET enabled_tools = ARRAY[
    'tool_get_watchlist',
    'tool_get_longterm_config',
    'tool_get_price_data',
    'tool_get_valuation',
    'tool_get_financial_health',
    'tool_read_research'
],
    updated_at = NOW()
WHERE agent_key = 'longterm';

-- 4. Insert longterm_review agent config

INSERT INTO agent_prompts (
    agent_key, agent_name, description, system_prompt,
    model_tier, model_id, temperature, output_retries, enabled_tools, is_active
) VALUES (
    'longterm_review',
    'Long-Term Review Agent',
    'Monthly agent for longterm watchlist automation.',
    'You are a senior Vietnamese equity analyst conducting monthly long-term portfolio reviews. Review each stock, generate research sections, validate entry zones and conviction levels, evaluate new candidates, and flag removals.',
    'heavy',
    NULL,
    0.3,
    2,
    ARRAY[
        'tool_get_watchlist',
        'tool_get_valuation',
        'tool_get_financial_health',
        'tool_get_financial_comparison',
        'tool_search_articles',
        'tool_read_research'
    ],
    TRUE
)
ON CONFLICT (agent_key) DO UPDATE
SET
    agent_name     = EXCLUDED.agent_name,
    description    = EXCLUDED.description,
    system_prompt  = EXCLUDED.system_prompt,
    model_tier     = EXCLUDED.model_tier,
    temperature    = EXCLUDED.temperature,
    output_retries = EXCLUDED.output_retries,
    enabled_tools  = EXCLUDED.enabled_tools,
    is_active      = EXCLUDED.is_active,
    updated_at     = NOW();
