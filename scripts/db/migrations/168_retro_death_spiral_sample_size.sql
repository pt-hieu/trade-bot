-- Retro generator: resolve death spiral vs small sample conflict
-- Old death spiral section overrode the n<10 rule, producing premature parameter changes
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    '## DEATH SPIRAL DETECTION
If the system produced 0 new entries for 2+ consecutive days, TOMORROW''S EDGE MUST aim to LOOSEN constraints:
- Evidence that the quality bar is above market reality (no picks passing for days)
- Correct action: lower R:R threshold slightly, or broaden pattern criteria
- Example rule: "Accept R:R >= 3.5 for BOUNCE setups with hammer pattern + volume confirmation"
- FORBIDDEN action: "Skip all BUY signals" / "Avoid all entries" / "Wait for clearer setups"
A system that never trades is broken. Consecutive zero-entry days = the bar is miscalibrated, not that the market has no opportunities.',
    '## DEATH SPIRAL DETECTION
If the system produced 0 new entries for 2+ consecutive days:
- OBSERVE: Note "Death spiral detected: 0 entries for N consecutive days"
- DIAGNOSE: Cite the specific constraint blocking entries (R:R threshold, entry gap, pattern filter)
- DO NOT propose parameter changes if total evaluated recommendations < 10 (n < 10)
- If n >= 10: propose a QUALITY FILTER loosening (e.g., "Lower R:R from 3.5 to 3.0"). Evidence required.
- If n < 10: write "INSUFFICIENT SAMPLE (n=X) for parameter change — maintain current rules, observe 3+ more sessions"
FORBIDDEN: Proposing threshold changes on n < 10 regardless of consecutive zero-entry days.
FORBIDDEN: "Skip all BUY signals" / "Avoid all entries" / "Wait for clearer setups"
A system that never trades is broken. But premature parameter changes on small samples are equally dangerous.'
)
WHERE agent_key = 'retro_generator'
AND system_prompt LIKE '%DEATH SPIRAL DETECTION%';
