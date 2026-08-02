-- Migration 068: Inter-day critic checklist item
-- Updates critic system prompt to include checklist item 15: Inter-Day Consistency
-- This ensures the critic flags EXIT→TRIM drifts, stop regressions, unfollowed exits

UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## Checklist Item 15: Inter-Day Consistency\nWhen inter-day drift data is provided in CONTEXT:\n- [interday_drift]: Flag if action downgraded (EXIT→TRIM, EXIT→HOLD, TRIM→HOLD) without underlying data change (same P/L, same price)\n- [stop_regression]: Flag if stop level was loosened by >5% without justification\n- [unfollowed_exit]: Flag if EXIT was recommended yesterday but holding still appears today'
WHERE agent_key = 'critic';
