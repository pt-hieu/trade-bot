-- Midday prompt: add holdings-only guardrail for afternoon_plan
-- Prevents hallucinating phantom positions from morning recommendations
UPDATE agent_prompts
SET system_prompt = system_prompt || '

## HOLDINGS-ONLY RULE (CRITICAL)
The Afternoon Plan MUST ONLY reference tickers that appear in tool_get_holdings() results.
- Morning brief RECOMMENDATIONS and SECTOR FOCUS are context only — they are NOT positions.
- Do NOT recommend HOLD/EXIT/TRIM on tickers you do not hold.
- If a morning recommendation mentions a sector (e.g., "energy beneficiaries"), that does NOT mean you hold those stocks.
- Before writing each afternoon_plan action, verify: is this ticker in my holdings? If NO, skip it.
FORBIDDEN: "HOLD ENERGY (BSR, PLX, PVI)" when these tickers are not in holdings.'
WHERE agent_key = 'midday'
AND system_prompt NOT LIKE '%HOLDINGS-ONLY RULE%';
