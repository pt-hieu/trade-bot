-- Migration 060: Fix longterm agent tools
-- Root cause: enabled_tools was empty, agent hallucinated without data
-- Fix: register tools needed to actually fetch watchlist + technicals

UPDATE agent_prompts
SET enabled_tools = ARRAY[
    'tool_get_watchlist',
    'tool_get_longterm_config',
    'tool_get_technicals',
    'tool_read_research'
]
WHERE agent_key = 'longterm';
