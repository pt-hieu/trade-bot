-- 091_enrichment_tools.sql
-- Add enrichment tools (flow, insider, RS) to sector and position agent enabled_tools.
-- Phase 2 of Quantitative Edge Roadmap.

UPDATE agent_prompts
SET enabled_tools = array_cat(enabled_tools, ARRAY['tool_get_flow', 'tool_get_insider', 'tool_get_relative_strength'])
WHERE agent_key IN ('sector', 'positions_technical', 'positions_value', 'positions_thesis')
  AND NOT ('tool_get_flow' = ANY(enabled_tools));

UPDATE agent_prompts
SET enabled_tools = array_cat(enabled_tools, ARRAY['tool_get_flow', 'tool_get_relative_strength'])
WHERE agent_key = 'synthesis'
  AND NOT ('tool_get_flow' = ANY(enabled_tools));
