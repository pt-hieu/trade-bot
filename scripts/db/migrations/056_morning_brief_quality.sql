-- Migration 056: Morning Brief Quality Fixes
-- 1. Positions: add pre-computed trailing stop instructions
-- 2. Synthesis: bifurcate swing R:R vs longterm entry zone logic
-- 3. Critic: add longterm R:R exception

-- 1. Positions agent: add trailing stop instructions before entry-based stop rules
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    '## Entry-Based Stop Rules
- If pct_from_entry >= +5%: Recommend breakeven_stop (protect gains)
- If pct_from_entry >= +10%: Recommend stop above entry (lock in profit)
- Always show "Entry: X | Current: Y (+Z%)" in alert',
    '## PRE-COMPUTED TRAILING STOPS (MANDATORY)
You receive pre-computed trailing stops for each holding in the user prompt.
These are deterministic — NEVER override them with your own calculation.
- LONGTERM + stop_type="none": Report "No stop — LONGTERM HOLD". Do NOT invent a stop.
- LONGTERM + action_hint="REVIEW_CONCENTRATION": Flag weight risk in alert.
- SWING + stop_type="trailing_*": Use the pre-computed stop level exactly.
- SWING + stop_type="technical": Use levels.swing_low with 2% buffer.
- SWING + stop_type="breakeven": Use entry price as stop.

## Entry-Based Stop Rules (Legacy — use pre-computed stops when available)
- If pct_from_entry >= +5%: Recommend breakeven_stop (protect gains)
- If pct_from_entry >= +10%: Recommend stop above entry (lock in profit)
- Always show "Entry: X | Current: Y (+Z%)" in alert'
)
WHERE agent_key = 'positions';

-- 2a. Synthesis agent: bifurcate R:R rule
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    '## Trading Rules
- Max risk per trade: 200,000 VND
- R:R minimum: 3:1 (REJECT any BUY with lower R:R)
- Cash reserve: 10M VND (NEVER touch)
- Max concurrent positions: 3',
    '## Trading Rules
- Max risk per trade: 200,000 VND
- R:R minimum 3:1 applies to TOP PICKS (swing trades) ONLY
- LONG-TERM PORTFOLIO uses entry zone logic — NOT swing R:R thresholds
- Cash reserve: 10M VND (NEVER touch)
- Max concurrent positions: 3'
)
WHERE agent_key = 'synthesis';

-- 2b. Synthesis agent: update LONG-TERM PORTFOLIO section
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    'LONG-TERM PORTFOLIO
- Stocks at/near entry zones from pre-computed analysis
- EXCLUDE tickers already in MY HOLDINGS',
    'LONG-TERM PORTFOLIO
- From pre-computed long-term analysis (gap_pct + zone status)
- BUY ZONE (gap <= 0%): "TICKER at Xk — IN entry zone (<Yk). Prepare capital."
- NEAR ENTRY (gap 0-5%): "TICKER at Xk — Z% above zone. Watch for pullback."
- WATCH/WAIT: One-liner or omit
- Do NOT apply R:R filter to long-term entries
- Mention structural catalysts (FTSE upgrade etc.) if relevant
- EXCLUDE tickers already in MY HOLDINGS'
)
WHERE agent_key = 'synthesis';

-- 3. Critic agent: add longterm R:R exception
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    '### 1. R:R Ratio Enforcement (CRITICAL)
For every BUY recommendation in TOP PICKS:
- Entry, Stop, Target MUST have actual numbers (not ranges or "around X")
- R:R = (Target - Entry) / (Entry - Stop) MUST be >= 3.0
- If R:R < 3.0 or calculation is missing/wrong, flag as [invalid_rr] or [missing_rr]',
    '### 1. R:R Ratio Enforcement (CRITICAL)
For every BUY recommendation in TOP PICKS:
- Entry, Stop, Target MUST have actual numbers (not ranges or "around X")
- R:R = (Target - Entry) / (Entry - Stop) MUST be >= 3.0
- If R:R < 3.0 or calculation is missing/wrong, flag as [invalid_rr] or [missing_rr]

NOTE: R:R enforcement applies to TOP PICKS (swing) ONLY.
LONG-TERM PORTFOLIO entries use entry zone logic (gap_pct to entry zone).
Do NOT flag long-term entries for missing R:R — they use different criteria.'
)
WHERE agent_key = 'critic';
