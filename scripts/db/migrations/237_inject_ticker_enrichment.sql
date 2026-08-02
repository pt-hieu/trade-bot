-- Migration 237: Remove per-ticker enrichment tools from agents (now context-injected)
-- Type: Data
-- Rollback: array_append the tools back to enabled_tools
--
-- Per-ticker tools (technicals, flow, insider, RS) are now batch-fetched in Phase 0
-- and injected as compact structured ticker briefings into agent prompts.
-- Agents that only used these tools for data access no longer need them.

-- Sector technical analyst — technicals + RS now in ticker briefings
UPDATE agent_prompts
SET enabled_tools = array_remove(
        array_remove(
            array_remove(enabled_tools, 'tool_get_ticker_data'),
            'tool_get_relative_strength'),
        'tool_get_technicals'),
    updated_at = NOW()
WHERE agent_key = 'sector_technical'
  AND ('tool_get_ticker_data' = ANY(enabled_tools)
    OR 'tool_get_relative_strength' = ANY(enabled_tools)
    OR 'tool_get_technicals' = ANY(enabled_tools));

-- Sector enrichment analyst — flow, insider, RS, flow_streak now in ticker briefings
UPDATE agent_prompts
SET enabled_tools = array_remove(
        array_remove(
            array_remove(
                array_remove(enabled_tools, 'tool_get_flow'),
                'tool_get_insider'),
            'tool_get_relative_strength'),
        'tool_get_flow_streak'),
    updated_at = NOW()
WHERE agent_key = 'sector_enrichment'
  AND ('tool_get_flow' = ANY(enabled_tools)
    OR 'tool_get_insider' = ANY(enabled_tools)
    OR 'tool_get_relative_strength' = ANY(enabled_tools)
    OR 'tool_get_flow_streak' = ANY(enabled_tools));

-- Position technical analyst — technicals, flow, insider, RS now injected
UPDATE agent_prompts
SET enabled_tools = array_remove(
        array_remove(
            array_remove(
                array_remove(enabled_tools, 'tool_get_technicals'),
                'tool_get_flow'),
            'tool_get_insider'),
        'tool_get_relative_strength'),
    updated_at = NOW()
WHERE agent_key = 'positions_technical'
  AND ('tool_get_technicals' = ANY(enabled_tools)
    OR 'tool_get_flow' = ANY(enabled_tools)
    OR 'tool_get_insider' = ANY(enabled_tools)
    OR 'tool_get_relative_strength' = ANY(enabled_tools));

-- Position value analyst — flow, insider, RS now injected
UPDATE agent_prompts
SET enabled_tools = array_remove(
        array_remove(
            array_remove(enabled_tools, 'tool_get_flow'),
            'tool_get_insider'),
        'tool_get_relative_strength'),
    updated_at = NOW()
WHERE agent_key = 'positions_value'
  AND ('tool_get_flow' = ANY(enabled_tools)
    OR 'tool_get_insider' = ANY(enabled_tools)
    OR 'tool_get_relative_strength' = ANY(enabled_tools));

-- Position thesis analyst — flow, insider, RS now injected
UPDATE agent_prompts
SET enabled_tools = array_remove(
        array_remove(
            array_remove(enabled_tools, 'tool_get_flow'),
            'tool_get_insider'),
        'tool_get_relative_strength'),
    updated_at = NOW()
WHERE agent_key = 'positions_thesis'
  AND ('tool_get_flow' = ANY(enabled_tools)
    OR 'tool_get_insider' = ANY(enabled_tools)
    OR 'tool_get_relative_strength' = ANY(enabled_tools));

-- Synthesis agents — flow, RS now injected
UPDATE agent_prompts
SET enabled_tools = array_remove(
        array_remove(enabled_tools, 'tool_get_flow'),
        'tool_get_relative_strength'),
    updated_at = NOW()
WHERE agent_key IN ('synthesis', 'synthesis_holdings')
  AND ('tool_get_flow' = ANY(enabled_tools)
    OR 'tool_get_relative_strength' = ANY(enabled_tools));

-- Bull/bear reviewers — technicals now injected
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_technicals'),
    updated_at = NOW()
WHERE agent_key IN ('bull_reviewer', 'bear_reviewer')
  AND 'tool_get_technicals' = ANY(enabled_tools);
