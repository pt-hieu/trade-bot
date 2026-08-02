-- Migration 127: Enable catalyst preview tool and update entry_strategist prompt

UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_catalyst_preview')
WHERE agent_key IN ('entry_strategist', 'synthesis')
AND NOT ('tool_get_catalyst_preview' = ANY(enabled_tools));

UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## Catalyst Awareness\nBefore finalizing entries, call tool_get_catalyst_preview() to check exposure.\nIf a recommended ticker has a HIGH-impact catalyst within 7 days:\n- Flag it clearly: "CATALYST RISK: [event] on [expected date]"\n- Consider reducing position size or waiting until after the event\nIf in doubt, a smaller entry now + add after catalyst resolution > full size into uncertainty.'
WHERE agent_key = 'entry_strategist'
AND system_prompt NOT LIKE '%Catalyst Awareness%';
