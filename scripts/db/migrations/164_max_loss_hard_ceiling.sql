-- 164_max_loss_hard_ceiling.sql
-- Add plan-type-specific max loss ceilings to positions_aggregator and midday prompts

-- Part 1: Add hard ceiling to positions_aggregator Fundamental Guard
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    '### Critical Override: Technical EXIT vs Value+Thesis HOLD
When Technical says EXIT (stop violated) but Value AND Thesis say HOLD:
- Final action: **EVALUATE** (not EXIT)',
    '### Critical Override: Technical EXIT vs Value+Thesis HOLD
When Technical says EXIT (stop violated) but Value AND Thesis say HOLD:
- FIRST CHECK max loss ceilings (from trading_config, injected in context):
  * SWING: If loss > swing_max_loss_pct → EXIT regardless. Fundamental Guard CANNOT override.
  * LONGTERM: If loss > longterm_catastrophic_pct → EXIT regardless. Thesis does not survive catastrophic loss.
- If loss is within ceiling but > 5%: Final action is **EVALUATE** (flag for human review)
- If loss < 5%: Final action is **HOLD** with "Fundamental Guard" note'
)
WHERE agent_key = 'positions_aggregator'
AND system_prompt NOT LIKE '%swing_max_loss_pct%';

-- Part 2: Add ceiling reference before Market Drawdown Guard
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    '## MARKET DRAWDOWN GUARD',
    '## MAX LOSS CEILING (NON-NEGOTIABLE, APPLIED BEFORE ALL OTHER RULES)
Two plan-type-specific ceilings from trading_config:
- SWING positions: swing_max_loss_pct (tighter — short-term risk management)
- LONGTERM positions: longterm_catastrophic_pct (wider — long-term thesis tolerance)
If ANY position loss exceeds its plan-type ceiling, the final action MUST be EXIT.
This overrides: Fundamental Guard, Market Drawdown Guard, Value analyst HOLD, Thesis analyst HOLD.
Reason: Capital preservation — letting a loss compound past the ceiling turns a manageable loss into a catastrophic one.

## MARKET DRAWDOWN GUARD'
)
WHERE agent_key = 'positions_aggregator'
AND system_prompt NOT LIKE '%MAX LOSS CEILING%';

-- Part 3: Add max loss hard stop to midday agent (plan-type aware)
UPDATE agent_prompts
SET system_prompt = system_prompt || '

## MAX LOSS HARD STOP (NON-NEGOTIABLE)
Two plan-type-specific ceilings from trading_config (provided in context):
- SWING positions: swing_max_loss_pct — tighter, short-term risk management
- LONGTERM positions: longterm_catastrophic_pct — wider, long-term thesis tolerance
If any position loss exceeds its plan-type ceiling, afternoon plan MUST recommend EXIT.
Fundamental Guard, value thesis, RSI oversold, and market drawdown context do NOT override these ceilings.
Format: "EXIT [TICKER] — MAX LOSS CEILING breached (-X.X% vs [SWING/LONGTERM] ceiling Y%). [HIGH confidence]"
'
WHERE agent_key = 'midday'
AND system_prompt NOT LIKE '%MAX LOSS HARD STOP%';
