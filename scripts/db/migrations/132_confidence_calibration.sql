-- Migration 132: Add CONFIDENCE CALIBRATION to 5 agents
--
-- Adds to:
--   midday:              [HIGH]/[MEDIUM]/[LOW] tags on afternoon_plan actions
--   watchlist_update:    Map confidence field to score thresholds + indicator alignment
--   positions_technical: Map 1-10 confidence to indicator alignment count
--   positions_value:     Map 1-10 confidence to fundamental metric health
--   positions_thesis:    Map 1-10 confidence to thesis + catalyst strength
--
-- sector already has SIGNAL CONFIDENCE from migration 111.
-- market_level already has regime_confidence 0-1 with self-calibration.
-- entry_strategist already has CALIBRATION SELF-CHECK from migration 113.
-- All UPDATEs are idempotent: guarded by NOT LIKE '%CONFIDENCE CALIBRATION%'

-- 1. midday: Calibrated tags on afternoon plan actions
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONFIDENCE CALIBRATION\nTag each afternoon_plan action with a confidence level:\n- [HIGH]:   Midday data strongly confirms morning plan (price, volume, and momentum all align)\n- [MEDIUM]: Midday data partially confirms (one indicator diverges — note it explicitly)\n- [LOW]:    Midday data contradicts morning plan — action is speculative, state why you still recommend it\nIf you cannot cite 2+ midday data points supporting an action, tag it [LOW].\nExample: "HOLD TCB — stop intact at 91k, midday RSI 44 stabilizing, volume 0.8x avg [MEDIUM]"'
WHERE agent_key = 'midday'
AND system_prompt NOT LIKE '%CONFIDENCE CALIBRATION%';

-- 2. watchlist_update: Map confidence field to calibrated rules
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONFIDENCE CALIBRATION\nSet the confidence field for each addition using calibrated rules:\n- "high":   Score >= 70 AND all key indicators align (RSI zone + sector regime + momentum + news)\n- "medium": Score 50-69, OR score >= 70 but one indicator conflicts (note it in reasons)\n- "low":    Score < 50 — should not appear in additions output (filtered by score threshold)\nIf a stock scores >= 50 but has 2+ conflicting indicators: set confidence to "medium" regardless of total score.'
WHERE agent_key = 'watchlist_update'
AND system_prompt NOT LIKE '%CONFIDENCE CALIBRATION%';

-- 3. positions_technical: Map 1-10 to indicator count alignment
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONFIDENCE CALIBRATION\nMap your 1-10 confidence score to indicator alignment count:\n- 8-10: 3+ independent technical signals converge (e.g. RSI zone + MACD cross + trend + volume confirmation)\n- 5-7:  2 signals align, 1 diverges — note the diverging signal explicitly in the view\n- 1-4:  Only 1 signal supports the action — note which signals are absent or contradicting\nNever assign confidence > 7 if you cannot cite at least 3 specific technical data points with values.\nConfidence 9-10 requires citing 4+ aligned indicators with specific values (e.g. "RSI 38, MACD bullish cross, above MA20, volume 1.6x").'
WHERE agent_key = 'positions_technical'
AND system_prompt NOT LIKE '%CONFIDENCE CALIBRATION%';

-- 4. positions_value: Map 1-10 to fundamental metric health
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONFIDENCE CALIBRATION\nMap your 1-10 confidence score to fundamental metric health:\n- 8-10: PE, ROE, margins, and D/E all in healthy range AND entry zone confirms value\n- 5-7:  3 of 4 metrics healthy, one concern noted explicitly in the view\n- 1-4:  2+ metrics in warning zone (ROE < 8%, PE > 25, or margins in consecutive decline)\nNever assign confidence > 7 if any single metric is in critical territory (ROE < 5%, D/E > 3.0, or revenue decline 2+ quarters).'
WHERE agent_key = 'positions_value'
AND system_prompt NOT LIKE '%CONFIDENCE CALIBRATION%';

-- 5. positions_thesis: Map 1-10 to thesis + catalyst strength
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONFIDENCE CALIBRATION\nMap your 1-10 confidence score to thesis and catalyst strength:\n- 8-10: Thesis fully intact, active catalysts confirmed in recent news, sector outlook positive\n- 5-7:  Thesis intact but catalysts are uncertain, delayed, or news is ambiguous\n- 1-4:  Thesis weakening — 1+ catalysts cancelled or reversed, sector headwinds emerging, or competitive threat identified\nNever assign confidence > 7 if you found negative news that directly impacts the investment thesis.\nA NEUTRAL view with confidence 5 is appropriate when no thesis information is available — do not assign high confidence without evidence.'
WHERE agent_key = 'positions_thesis'
AND system_prompt NOT LIKE '%CONFIDENCE CALIBRATION%';
