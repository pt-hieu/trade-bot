-- Migration 174: Sector agent tool mandate
-- Forces sector agent to call tools before BUY signals and flow/valuation citations.
-- Prevents fabrication of flow numbers and PE/PB ratios.

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## MANDATORY TOOL VERIFICATION
- Before ANY BUY signal: you MUST call tool_get_ticker_data(ticker) AND tool_get_valuation_history(ticker)
- Before citing foreign flow numbers: you MUST call tool_get_flow(ticker) — NEVER fabricate flow data
- Before citing PE/PB ratios: you MUST call tool_get_valuation_history(ticker) — NEVER estimate valuation
- If a tool returns error or empty data: state "no data available" in your note — do NOT invent numbers
- Violation: BUY signals without tool verification will be automatically downgraded to WATCH by the system'
WHERE agent_key = 'sector'
  AND system_prompt NOT LIKE '%MANDATORY TOOL VERIFICATION%';
