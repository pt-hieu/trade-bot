-- Migration 131: Add BULL/BEAR BALANCE to 4 agents
--
-- Adds to:
--   sector:          BUY note must include KEY RISK challenging the thesis
--   longterm:        BUY ZONE action must include specific counter-argument
--   watchlist_update: Addition reasons must include one bear case
--   longterm_review: risks section must genuinely challenge thesis
--
-- entry_strategist already has BULL/BEAR BALANCE from migration 111.
-- All UPDATEs are idempotent: guarded by NOT LIKE '%BULL/BEAR BALANCE%'

-- 1. sector: Require bear case in note field for every BUY signal
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## BULL/BEAR BALANCE\nFor every BUY signal, the note field must include a KEY RISK that genuinely challenges the thesis:\n- Name the single biggest reason this trade could fail — not a generic "market could drop"\n- Example: "RSI 38 at support 95k, hammer on 1.5x avg volume, banking HOT. KEY RISK: foreign net selling -200B in banking sector this week. [HIGH]"\nFor every AVOID signal: name what opportunity you would miss if the bear thesis is wrong.\nA BUY note without a specific, falsifiable risk factor is a hallucination flag.\nLLMs systematically overweight upside in financial analysis — KEY RISK corrects that bias.'
WHERE agent_key = 'sector'
AND system_prompt NOT LIKE '%BULL/BEAR BALANCE%';

-- 2. longterm: Require specific counter-argument for entry zone recommendations
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## BULL/BEAR BALANCE\nFor every BUY ZONE or NEAR ENTRY recommendation, the action field must include one specific counter-argument:\n- Not generic "market risk" — must name what company-specific or technical factor could invalidate the entry\n- Example: "Accumulate at 28k entry zone. RISK: ROE declining 2 consecutive quarters — may trigger exit criteria before position matures"\nFor WATCH recommendations (stock oversold but not yet actionable): name the specific bullish catalyst you would need to see before entering.\nBeing in BUY ZONE does not guarantee recovery — the counter-argument is the discipline check.'
WHERE agent_key = 'longterm'
AND system_prompt NOT LIKE '%BULL/BEAR BALANCE%';

-- 3. watchlist_update: Require one bear case in addition reasons
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## BULL/BEAR BALANCE\nFor each stock addition, the reasons list must include at least one bear case (0-point reason that names the risk):\n- Example: reasons=["RSI 35 at support (+30)", "Banking HOT sector (+15)", "RISK: NPL ratio rising, watch next quarter (+0)"]\nFor each removal, include one bull case you are consciously dismissing:\n- Example: reasons=["RSI 74 overbought (+40)", "Sector cooling (+20)", "COUNTER: strong Q4 earnings but momentum exhausted (+0)"]\nThis prevents systematic overweighting of bullish signals when building the additions list.'
WHERE agent_key = 'watchlist_update'
AND system_prompt NOT LIKE '%BULL/BEAR BALANCE%';

-- 4. longterm_review: Require genuine challenge in risks section
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## BULL/BEAR BALANCE\nThe risks section for each stock must genuinely challenge the thesis — not repeat generic sector or macro risks:\n- When recommending conviction UPGRADE: name the single biggest threat that could reverse it within 12 months\n- When recommending conviction DOWNGRADE: name the specific positive catalyst that would reverse it\n- For new stock ADDITIONS to watchlist: bear case must be company-specific, not "Vietnam macro risk" or "sector rotation"\nLLMs systematically underweight downside in financial analysis. A weak or generic risk section is a quality failure — challenge it actively before writing it.'
WHERE agent_key = 'longterm_review'
AND system_prompt NOT LIKE '%BULL/BEAR BALANCE%';
