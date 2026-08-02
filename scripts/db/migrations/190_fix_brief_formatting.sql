-- Migration 190: Fix brief formatting — remove citation tags + enforce standalone section headers
--
-- Bug 1: entry_strategist citation instruction causes [tool_name/field] to leak into Telegram
-- Bug 2: synthesis sub-agents write inline section headers that break Telegram parser
-- All UPDATEs are idempotent.

-- 1. entry_strategist: replace citation mandate with anti-citation rule
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    E'Each NEWS THAT MATTERS bullet MUST cite its source [tool_name/field].\nExample: "Foreign net sell -199B: AI regulation fears hit tech (FPT -3.2%) [articles: #42 Reuters] — sector flow confirms institutional rotation out [tool_get_flow/foreign_net]"\nBAD: "Foreign distribution seeing profit-taking despite index strength" (no source, no catalyst, no portfolio impact)',
    E'Each NEWS THAT MATTERS bullet must name the specific catalyst and connect to portfolio impact.\nExample: "Foreign net sell -199B: AI regulation fears hit tech (FPT -3.2%) — sector flow confirms institutional rotation out"\nBAD: "Foreign distribution seeing profit-taking despite index strength" (no catalyst, no portfolio impact)\nFORBIDDEN: Do NOT include [tool_name], [source], or any bracket citation tags in output — source attribution is internal only.'
)
WHERE agent_key = 'entry_strategist'
  AND system_prompt LIKE '%MUST cite its source [tool_name/field]%';

-- 2. entry_strategist: fix similar days citation format (remove tool reference)
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    E'- Format: "Similar days: X% win rate (source: tool_get_similar_days)"',
    E'- Format: "Similar days: X% win rate"'
)
WHERE agent_key = 'entry_strategist'
  AND system_prompt LIKE '%source: tool_get_similar_days%';

-- 3. synthesis_holdings: enforce standalone section headers
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    'PLAIN ASCII only. No markdown, no emojis, no headers with #.',
    E'PLAIN ASCII only. No markdown, no emojis, no headers with #.\nSection headers (MY HOLDINGS, LONG-TERM PORTFOLIO) must appear ALONE on their own line — no parenthetical notes, no colons, no inline content after the header name.'
)
WHERE agent_key = 'synthesis_holdings'
  AND system_prompt NOT LIKE '%must appear ALONE on their own line%';

-- 4. synthesis_picks: enforce standalone section headers
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    'PLAIN ASCII only. No markdown, no emojis, no headers with #.',
    E'PLAIN ASCII only. No markdown, no emojis, no headers with #.\nSection headers (TOP PICKS, SKIP THESE, WHAT TO DO TODAY) must appear ALONE on their own line — no parenthetical notes, no colons, no inline content after the header name.'
)
WHERE agent_key = 'synthesis_picks'
  AND system_prompt NOT LIKE '%must appear ALONE on their own line%';
