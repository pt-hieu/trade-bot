-- Migration 247: Fix stale tool_get_my_beliefs references in agent prompts
--
-- Root cause: Migration 238 removed tool_get_my_beliefs from enabled_tools
-- but did NOT update the system_prompt text. 4 agents still tell the LLM
-- to call a tool that doesn't exist, causing them to skip prior belief
-- review entirely and default to NEW (which gets auto-corrected to
-- REAFFIRMED, creating fake belief continuity).
--
-- Affected agents: sector_technical, sector_news, sector_enrichment, positions_value
-- Already fixed: positions_technical, positions_thesis (migration 245)
--
-- All operations are idempotent replace() calls.

BEGIN;

-- Fix 1: Replace tool_get_my_beliefs reference with context injection note
-- Same text across all 4 agents (from migration 209)
UPDATE agent_prompts
SET system_prompt = replace(
        system_prompt,
        'Before analyzing each ticker, retrieve your prior beliefs via tool_get_my_beliefs.',
        'Your prior beliefs are pre-loaded in the ticker briefings above. Review the YOUR PRIOR section for each ticker before forming today''s belief.'
    ),
    updated_at = NOW()
WHERE is_active = true
  AND system_prompt LIKE '%tool_get_my_beliefs%';

-- Fix 2: For sector agents, update the calibration reference
-- (sector_technical, sector_news, sector_enrichment have the longer form)
UPDATE agent_prompts
SET system_prompt = replace(
        system_prompt,
        'Check your accuracy via tool_get_belief_accuracy before finalizing',
        'Use base rate anchoring when uncertain'
    ),
    updated_at = NOW()
WHERE is_active = true
  AND agent_key IN ('sector_technical', 'sector_news', 'sector_enrichment')
  AND system_prompt LIKE '%Check your accuracy via tool_get_belief_accuracy before finalizing%';

-- Fix 3: For positions_value, update the shorter calibration reference
UPDATE agent_prompts
SET system_prompt = replace(
        system_prompt,
        'Check tool_get_belief_accuracy.',
        'Use base rate anchoring when uncertain.'
    ),
    updated_at = NOW()
WHERE is_active = true
  AND agent_key = 'positions_value'
  AND system_prompt LIKE '%Check tool_get_belief_accuracy.%';

COMMIT;
