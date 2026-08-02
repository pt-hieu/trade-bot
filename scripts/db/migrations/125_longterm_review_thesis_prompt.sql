-- Migration 125: Update longterm_review prompt for thesis tracking + enable tool_get_thesis

UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## Thesis Tracking (MANDATORY per stock)\nFor each reviewed stock, provide:\n1. thesis_pillars: 3-5 pillars, each with status INTACT/WEAKENING/BROKEN and specific evidence\n   - For each WEAKENING: state the path back to INTACT\n   - For each INTACT: state the specific risk of weakening\n2. kill_criteria: 2-3 specific, measurable conditions that would invalidate the thesis\n   Example: "ROE below 8% for 3 consecutive quarters"\n   Status: NOT_MET / WARNING / TRIGGERED\nBe specific — generic pillars like "good management" are not useful.'
WHERE agent_key = 'longterm_review'
AND system_prompt NOT LIKE '%Thesis Tracking%';

UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_thesis')
WHERE agent_key = 'positions_pev_alert'
AND NOT ('tool_get_thesis' = ANY(enabled_tools));
