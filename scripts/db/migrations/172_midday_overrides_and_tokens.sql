-- Migration 172: Midday override enforcement + max_tokens bump
-- Stop breaches must populate recommendation_overrides, not just afternoon_plan prose.
-- Midday output was truncated at 2048 tokens (finish_reason: length).

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## RECOMMENDATION OVERRIDES RULE (MANDATORY)
For EVERY position in Position Alerts with level_type STOP_BREACHED or urgency critical:
- You MUST add a RecommendationOverride with midday_status=CANCEL.
For EVERY ticker where your afternoon_plan mentions EXIT, TRIM, or CANCEL:
- You MUST add a corresponding RecommendationOverride entry.
An empty recommendation_overrides is ONLY acceptable if NO positions need changes.

Example:
recommendation_overrides: [
  {"ticker": "VHM", "morning_action": "HOLD", "midday_status": "CANCEL",
   "reason": "Stop breached at 93,000 -- price hit 88,400 intraday (-5.2%)"}
]'
WHERE agent_key = 'midday'
  AND system_prompt NOT LIKE '%RECOMMENDATION OVERRIDES RULE%';

UPDATE agent_prompts
SET max_tokens = 4096
WHERE agent_key = 'midday'
  AND (max_tokens IS NULL OR max_tokens < 4096);
