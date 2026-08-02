-- 038: Add global ticker dedup rule to synthesis prompt
-- Prevents same ticker from appearing in multiple brief sections
-- Priority: MY HOLDINGS > TOP PICKS > LONG TERM > SKIP THESE > WHAT TO DO

-- Step 1: Update the prompt
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    E'TOP PICKS (max 5)\n- Each with Entry, Stop, Target, R:R ratio\n- All must have R:R >= 3.0',
    E'## GLOBAL TICKER DEDUP RULE (CRITICAL)\nEach ticker may appear in EXACTLY ONE section. Use this priority:\n1. MY HOLDINGS (highest - always wins for active positions)\n2. TOP PICKS\n3. LONG-TERM PORTFOLIO\n4. SKIP THESE\n5. WHAT TO DO TODAY (lowest - reference only, never duplicate entries from above)\nIf a ticker qualifies for multiple sections, place it in the highest-priority section only.\nWHAT TO DO TODAY references tickers from other sections by name without repeating full entries.\nExample: \"Watch VHM at support\" is OK if VHM is already in MY HOLDINGS.\n\nTOP PICKS (max 5)\n- Each with Entry, Stop, Target, R:R ratio\n- All must have R:R >= 3.0'
),
    updated_at = NOW()
WHERE agent_key = 'synthesis';

-- Step 2: Record version in agent_prompt_versions
INSERT INTO agent_prompt_versions (prompt_id, version_number, system_prompt, change_note)
SELECT
    p.id,
    COALESCE((SELECT MAX(version_number) FROM agent_prompt_versions WHERE prompt_id = p.id), 0) + 1,
    p.system_prompt,
    'Add global ticker dedup rule — each ticker in exactly one section (priority: MY HOLDINGS > TOP PICKS > LONG-TERM > SKIP THESE > WHAT TO DO)'
FROM agent_prompts p
WHERE p.agent_key = 'synthesis';
