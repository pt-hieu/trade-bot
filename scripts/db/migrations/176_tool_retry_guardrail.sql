-- Migration 176: Add retry guardrail to all tool-using agents
-- Prevents LLMs from retrying identical failed tool calls (sector burned 133K tokens from 11x retries)
-- Idempotent: guarded by NOT LIKE check

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## TOOL RETRY GUARDRAIL
If a tool call returns an error or empty result:
- Do NOT retry the exact same call with identical arguments.
- Try alternative arguments OR proceed without that data.
- After 2 consecutive failed tool calls, stop calling tools and work with available data.
- State explicitly what data is missing rather than retrying indefinitely.'
WHERE enabled_tools != '{}'
  AND enabled_tools IS NOT NULL
  AND is_active = TRUE
  AND system_prompt NOT LIKE '%TOOL RETRY GUARDRAIL%';
