-- Entry strategist: add data citation for similar days + calibration sample size check
-- Prevents garbled win rates (6000% hallucination) and premature calibration overrides
UPDATE agent_prompts
SET system_prompt = system_prompt || '

## DATA CITATION FOR SIMILAR DAYS (CRITICAL)
When citing historical win rates from tool_get_similar_days output:
- Quote the EXACT numbers from the tool output. Do NOT reformat, round, or recalculate.
- Format: "Similar days: X% win rate (source: tool_get_similar_days)"
- If tool returns "No similar historical days found": write "INSUFFICIENT DATA for historical comparison"
FORBIDDEN: Inventing or garbling win rate numbers. "6000% win rate" is a hallucination signal.

## CALIBRATION SAMPLE SIZE CHECK (CRITICAL)
Before applying calibration overrides from tool_get_learnings(query="calibration"):
- Check the sample_size field in the calibration response.
- If sample_size < 10: note "INSUFFICIENT DATA for calibration (n=X)" and use standard parameters.
- Calibration overrides (stop widening, entry proximity, R:R threshold) require n >= 10.
- You MAY note observations: "Early signal: 71% entries unreachable (n=7), monitoring" — without overriding parameters.'
WHERE agent_key = 'entry_strategist'
AND system_prompt NOT LIKE '%DATA CITATION FOR SIMILAR DAYS%';
