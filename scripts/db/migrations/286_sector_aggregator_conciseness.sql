-- Migration 286: Add OUTPUT LENGTH RULES to sector_aggregator prompt
-- Fixes: 96K token runaway for mixed/industrial sectors (2026-04-06)
-- Root cause: unbounded string fields + no conciseness constraints in prompt

UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## OUTPUT LENGTH RULES (MANDATORY)\n- note: max 1-2 sentences (what drives the signal)\n- key_risk: max 1 sentence (the strongest counter-argument)\n- summary: max 2-3 sentences (sector-level theme)\n- belief_narrative: max 2 sentences (why this direction)\n- disagreement_note: max 1 sentence (where analysts split)\nBe direct. No preambles, no hedging paragraphs, no restating the input.\n',
    updated_at = NOW()
WHERE agent_key = 'sector_aggregator';
