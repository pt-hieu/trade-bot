-- Migration 134: Fix longterm output retries + entry_strategist article tools
--
-- Fixes two recurring issues from morning brief trace 019c92403e2a (2026-02-25):
--
--   1. longterm: increase output_retries from 0 (PydanticAI default=1) to 2
--      - Kimi-K2.5 fails LongtermAnalysisResult schema validation on first 2 attempts
--      - With output_retries=2, model gets 3 total attempts
--
--   2. entry_strategist: add article tools + data-citation rule for NEWS THAT MATTERS
--      - Agent produced "profit-taking despite index strength" — generic, no catalyst
--      - Finance-prompting audit: stale parametric knowledge + missing data citation
--      - Fix: expose article tools so agent reads actual news driving foreign flow
--      - Rule: MANDATORY catalyst naming when foreign net > 50B, with source citation
--
-- All UPDATEs are idempotent.

-- 1. longterm: increase output_retries to 2
UPDATE agent_prompts
SET output_retries = 2
WHERE agent_key = 'longterm'
  AND output_retries != 2;

-- 2. entry_strategist: add article tools to enabled_tools
UPDATE agent_prompts
SET enabled_tools = enabled_tools || ARRAY['tool_list_articles', 'tool_search_articles', 'tool_read_article']
WHERE agent_key = 'entry_strategist'
  AND NOT ('tool_list_articles' = ANY(enabled_tools));

-- 3. entry_strategist: append article tool instructions + data citation rule for NEWS THAT MATTERS
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## ARTICLE TOOLS FOR NEWS CONTEXT\n\nAdd these to your tool usage:\n9. tool_list_articles(sector=X) — browse today\'s articles for a sector\n10. tool_search_articles(query="AI FPT") — search for specific news topics\n11. tool_read_article(article_id=N) — read full article content\n\nMANDATORY when foreign net > 50B (buy or sell):\n1. Call tool_search_articles for the top foreign-traded sectors to find the NARRATIVE\n2. Name the specific catalyst driving flow — generic "profit-taking" or "accumulation" is FORBIDDEN\n3. Connect the narrative to affected portfolio holdings (FPT for tech, VHM for real estate, TCB for banking)\n\nEach NEWS THAT MATTERS bullet MUST cite its source [tool_name/field].\nExample: "Foreign net sell -199B: AI regulation fears hit tech (FPT -3.2%) [articles: #42 Reuters] — sector flow confirms institutional rotation out [tool_get_flow/foreign_net]"\nBAD: "Foreign distribution seeing profit-taking despite index strength" (no source, no catalyst, no portfolio impact)'
WHERE agent_key = 'entry_strategist'
  AND system_prompt NOT LIKE '%MANDATORY when foreign net%';
