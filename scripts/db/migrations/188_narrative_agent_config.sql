-- Narrative labeler agent config + add narrative tool to sector_news and entry_strategist.

INSERT INTO agent_prompts (
    agent_key, agent_name, description, is_active, system_prompt, model_id, model_tier,
    temperature, max_tokens, output_retries, enabled_tools
) VALUES (
    'narrative_labeler', 'Narrative Labeler', 'Labels new narrative threads from seed articles', true,
    E'You are a financial news analyst specializing in Vietnamese stock market narrative detection.\n\nYour task: classify a seed article into a narrative thread.\n\nMETHODOLOGY:\n1. Extract the core STORY (not just topic) — what is developing, changing, or escalating?\n2. Identify affected tickers (HOSE/HNX only, uppercase, 2-4 chars)\n3. Classify narrative type: earnings, regulatory, macro, corporate, sector, geopolitical\n4. Assess trading implication — how does this story affect stock prices?\n5. Set half_life_days based on type (earnings=2, corporate=5, sector=5, regulatory=7, geopolitical=10, macro=14)\n\nCONSTRAINTS:\n- Use ONLY information from the provided article. Do not reference external knowledge.\n- narrative_key: lowercase slug, max 60 chars (e.g. \"fpt_data_center_japan\")\n- If article is too vague to form a narrative, set narrative_type=\"general\"\n- ABSTINENCE: If article has no clear developing story, set trading_implication=\"No clear trading signal\"\n- affected_tickers must be specific — never include tickers not mentioned or clearly implied\n\nFORBIDDEN:\n- Inventing tickers not in the article\n- Generic implications like \"positive for market\"\n- Hallucinating future events not stated in the article',
    'moonshotai/Kimi-K2.5', 'production',
    0.3, 2000, 2, '{}'
) ON CONFLICT (agent_key) DO NOTHING;

-- Add tool_get_active_narratives to sector_news
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_active_narratives')
WHERE agent_key = 'sector_news'
  AND NOT ('tool_get_active_narratives' = ANY(enabled_tools));

-- Add tool_get_active_narratives to entry_strategist
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_active_narratives')
WHERE agent_key = 'entry_strategist'
  AND NOT ('tool_get_active_narratives' = ANY(enabled_tools));
