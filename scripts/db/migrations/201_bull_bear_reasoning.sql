-- Migration 201: Add bull/bear reasoning to ensemble agents
-- Lost during ensemble refactor (migrations 175, 178). Restores structured
-- counter-argument requirements using pre-mortem and counter-thesis techniques.
-- Research: pre-mortem reduces overconfidence ~30%, structured counterarguments
-- beat generic "be unbiased" prompts, LLMs are MORE susceptible to anchoring.

-- ── DDL: Add counter_thesis column to ensemble votes audit table ───────────
-- NOTE: This is DDL — requires owner connection URL to apply.

ALTER TABLE position_ensemble_votes
ADD COLUMN IF NOT EXISTS counter_thesis TEXT;

-- ── (a) sector_aggregator: BULL/BEAR BALANCE + PRE-MORTEM ──────────────────

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## BULL/BEAR BALANCE (MANDATORY)
For every ticker signal, populate the key_risk field:
- BUY → key_risk MUST be the strongest argument AGAINST buying (not a minor footnote)
- AVOID → key_risk MUST name the opportunity you would miss if wrong
- WATCH/WAIT → key_risk MUST state which direction the ambiguity could break

## PRE-MORTEM STEP
Before finalizing each BUY signal, assume you recommended this stock and it LOST 15% in 2 weeks.
List the most likely reason it failed. This becomes your key_risk.
If the pre-mortem reason is strong enough to change your mind, downgrade to WATCH.
A BUY without a genuinely challenging key_risk is incomplete.'
WHERE agent_key = 'sector_aggregator'
  AND is_active = true
  AND system_prompt NOT LIKE '%BULL/BEAR BALANCE%';


-- ── (b) sector_technical: KEY RISK field ───────────────────────────────────

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## KEY RISK (MANDATORY)
For every ticker in your analysis, populate the key_risk field:
- Your strongest counter-argument to your own signal
- Must be specific (price levels, catalysts, timing) not generic ("market could drop")
- A good key_risk genuinely challenges the thesis, not a footnote
- BUY with weak/missing key_risk will be flagged by the aggregator'
WHERE agent_key = 'sector_technical'
  AND is_active = true
  AND system_prompt NOT LIKE '%KEY RISK (MANDATORY)%';


-- ── (c) sector_news: KEY RISK field ────────────────────────────────────────

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## KEY RISK (MANDATORY)
For every ticker in your analysis, populate the key_risk field:
- Your strongest counter-argument to your own signal
- Must be specific (catalyst risks, regulatory timeline, sentiment reversal) not generic
- A good key_risk genuinely challenges the thesis, not a footnote
- BUY with weak/missing key_risk will be flagged by the aggregator'
WHERE agent_key = 'sector_news'
  AND is_active = true
  AND system_prompt NOT LIKE '%KEY RISK (MANDATORY)%';


-- ── (d) sector_enrichment: KEY RISK field ──────────────────────────────────

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## KEY RISK (MANDATORY)
For every ticker in your analysis, populate the key_risk field:
- Your strongest counter-argument to your own signal
- Must be specific (flow reversal risk, insider timing, valuation ceiling) not generic
- A good key_risk genuinely challenges the thesis, not a footnote
- BUY with weak/missing key_risk will be flagged by the aggregator'
WHERE agent_key = 'sector_enrichment'
  AND is_active = true
  AND system_prompt NOT LIKE '%KEY RISK (MANDATORY)%';


-- ── (e) positions_aggregator: COUNTER-THESIS + PRE-MORTEM ──────────────────

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## COUNTER-THESIS (MANDATORY)
For every alert, populate the counter_thesis field:
- TRIM/EXIT → what upside would be missed? What catalyst could reverse the decline?
- ADD → what risk makes adding here premature?
- HOLD → what signal would change this to EXIT?
The counter_thesis must be specific enough to define a "what would change my mind" trigger.

## PRE-MORTEM FOR EXIT/TRIM
Before recommending EXIT or TRIM, assume the stock RECOVERS 20% in the next month.
What was the most likely reason for recovery? If that reason is plausible, consider:
- Downgrading EXIT to TRIM
- Downgrading TRIM to HOLD with a tighter stop
An EXIT/TRIM without a genuinely challenging counter_thesis is incomplete.'
WHERE agent_key = 'positions_aggregator'
  AND is_active = true
  AND system_prompt NOT LIKE '%COUNTER-THESIS%';


-- ── (f) positions sub-analysts: COUNTER-THESIS field ───────────────────────

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## COUNTER-THESIS (MANDATORY)
For every position, populate the counter_thesis field:
- The strongest argument AGAINST your recommended action
- Must be specific (price levels, catalysts, timing) not generic
- Example for TRIM: "but support at 115k is holding and Q2 catalysts could push to 130k"
- Example for HOLD: "but if volume stays below 20-day avg for 3 more sessions, thesis weakens"'
WHERE agent_key = 'positions_technical'
  AND is_active = true
  AND system_prompt NOT LIKE '%COUNTER-THESIS%';

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## COUNTER-THESIS (MANDATORY)
For every position, populate the counter_thesis field:
- The strongest argument AGAINST your recommended action
- Must be specific (valuation, fair value range, margin of safety) not generic
- Example for EXIT: "but P/B at 0.8x is below 5-year avg of 1.2x, suggesting value floor"
- Example for ADD: "but earnings revision risk in next quarter could compress multiples"'
WHERE agent_key = 'positions_value'
  AND is_active = true
  AND system_prompt NOT LIKE '%COUNTER-THESIS%';

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## COUNTER-THESIS (MANDATORY)
For every position, populate the counter_thesis field:
- The strongest argument AGAINST your recommended action
- Must be specific (thesis catalysts, sector outlook, competitive dynamics) not generic
- Example for TRIM: "but sector rotation into real estate just starting, VHM is cycle leader"
- Example for HOLD: "but if land bank monetization delays past Q3, growth thesis breaks"'
WHERE agent_key = 'positions_thesis'
  AND is_active = true
  AND system_prompt NOT LIKE '%COUNTER-THESIS%';


-- ── (g) synthesis_picks: CONVICTION TEST ───────────────────────────────────

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## CONVICTION TEST
For each TOP PICK, include one sentence: "RISK: [strongest reason this pick fails]"
For each SKIP, include one sentence: "MISS: [what opportunity you would lose if wrong]"
This is NOT optional. A pick without a RISK line is incomplete.
Use the key_risk from sector analysis as a starting point, then sharpen it.'
WHERE agent_key = 'synthesis_picks'
  AND is_active = true
  AND system_prompt NOT LIKE '%CONVICTION TEST%';


-- ── (h) synthesis_holdings: COUNTER-THESIS FOR ACTIONS ─────────────────────

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## COUNTER-THESIS FOR ACTIONS
When recommending TRIM or EXIT on any holding:
- State what upside remains if the stock recovers
- Name the specific catalyst or level that would invalidate the exit thesis
- Use the COUNTER field from POSITION ALERTS as your starting point
- Example: "TRIM VHM -- but support at 115k is holding and project launches in Q2 could push to 130k"
When recommending HOLD through a drawdown:
- State the specific level where HOLD becomes wrong'
WHERE agent_key = 'synthesis_holdings'
  AND is_active = true
  AND system_prompt NOT LIKE '%COUNTER-THESIS FOR ACTIONS%';


-- ── (i) critic: THESIS QUALITY CHECK ───────────────────────────────────────

UPDATE agent_prompts
SET system_prompt = system_prompt || '

## THESIS QUALITY CHECK
For every BUY pick and every EXIT/TRIM recommendation in the brief:
- Verify a counter-argument exists (RISK line for picks, counter-thesis for positions)
- If missing: flag as MAJOR issue -- "Missing counter-thesis for [action] [ticker]"
- If counter-argument is generic ("market risk", "could go down"): flag as MINOR -- "Weak counter-thesis for [ticker]"
A brief where all recommendations have strong counter-arguments is higher quality.'
WHERE agent_key = 'critic'
  AND is_active = true
  AND system_prompt NOT LIKE '%THESIS QUALITY CHECK%';
