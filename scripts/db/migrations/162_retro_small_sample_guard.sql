-- 162_retro_small_sample_guard.sql
-- Harden TOMORROW'S EDGE: block rule proposals on n<10
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    'For TOMORROW''S EDGE:
- If action stats show n < 10, write a QUALITY FILTER, not a signal ban',
    'For TOMORROW''S EDGE:
- HARD RULE: If ALL actionable patterns have n < 10, write "INSUFFICIENT SAMPLE (n=X) -- maintain current rules, monitor 3+ more days"
- Do NOT propose parameter changes (R:R thresholds, position sizing, signal bans) when n < 10
- You MAY note observations: "Early signal: LIMIT_BUY 0/7 (n=7), monitoring" -- without proposing changes
- If action stats show n >= 10, write a QUALITY FILTER, not a signal ban'
)
WHERE agent_key = 'retro_generator'
AND system_prompt NOT LIKE '%HARD RULE: If ALL actionable patterns%';
