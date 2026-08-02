-- Migration 133: Add FEW-SHOT EXAMPLES to 3 agents
--
-- Adds to:
--   sector:  Signal classification good/bad examples with reasoning
--   longterm: Entry zone analysis good/bad examples
--   midday:  Afternoon plan good/bad examples with midday prices
--
-- positions_technical already has examples from migration 100.
-- alert_registrar already has examples from migration 117.
-- All UPDATEs are idempotent: guarded by NOT LIKE '%FEW-SHOT EXAMPLES%'

-- 1. sector: Signal classification examples
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## FEW-SHOT EXAMPLES\n\n<good_example>\nTCB: BUY\nNote: RSI 38 at support 95k, hammer on 1.5x avg volume, banking HOT. MACD bullish cross confirmed. KEY RISK: foreign net selling in banking sector -200B VND this week — momentum reversal risk. [HIGH]\n<reasoning>\nGood: cites 4 specific data points (RSI value, support level, pattern+volume confirmation, sector regime). Includes KEY RISK that genuinely challenges the thesis with a specific, measurable factor. Confidence [HIGH] is justified by 4/4 alignment. Note is actionable and verifiable.\n</reasoning>\n</good_example>\n\n<bad_example>\nTCB: BUY\nNote: Stock looks oversold and ready to bounce. Banking sector is generally strong.\n<reasoning>\nBad: no specific RSI value, no support level cited, no pattern or volume confirmation named. "Looks oversold" is subjective and unverifiable. No KEY RISK. No confidence tag. This note would apply to any stock at any time — it carries zero information.\n</reasoning>\n</bad_example>'
WHERE agent_key = 'sector'
AND system_prompt NOT LIKE '%FEW-SHOT EXAMPLES%';

-- 2. longterm: Entry zone analysis examples
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## FEW-SHOT EXAMPLES\n\n<good_example>\nFPT: BUY ZONE — Current price 88k vs entry zone 90k (gap -2.2%). RSI 33 with hammer on MA20. Trend: sideways with support holding. Conviction: High.\nAction: Accumulate at current levels in tranches. RISK: Tech sector rotation cooling this month and RSI still falling — wait for RSI to stabilize above 35 before adding second tranche.\n<reasoning>\nGood: specific price, entry zone, and gap percentage cited. RSI cited with pattern and MA context. Conviction level assigned. Action is specific (tranches). RISK is specific and falsifiable — names exact RSI threshold for re-evaluation.\n</reasoning>\n</good_example>\n\n<bad_example>\nFPT: BUY ZONE — Good company trading below entry. Recommend buying.\n<reasoning>\nBad: no current price, no entry zone level, no gap percentage, no RSI, no pattern, no trend direction. "Good company" is not analysis — it is an assertion without evidence. No risk factor. Missing every data point needed for an actionable recommendation.\n</reasoning>\n</bad_example>'
WHERE agent_key = 'longterm'
AND system_prompt NOT LIKE '%FEW-SHOT EXAMPLES%';

-- 3. midday: Afternoon plan examples with actual midday prices
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## FEW-SHOT EXAMPLES\n\n<good_example>\nmorning_reflection: Morning BUY on VHM at 42k entry played out — midday high 42.8k (+1.9%), RSI stabilizing at 44. TCB stop at 91k held, midday low 91.5k with volume 0.9x avg.\nafternoon_plan: HOLD VHM — stop intact at 40.5k, midday momentum positive, target 44k [HIGH]. CANCEL morning WATCH on NLG — midday broke below 25k support with 1.4x volume, momentum bearish, setup invalidated [HIGH].\n<reasoning>\nGood: uses actual midday prices from tool_get_midday_prices. Explicitly compares morning entry to midday outcome. Cites specific stops and targets. Cancels a deteriorated setup with technical reasoning. Confidence tags applied to each action.\n</reasoning>\n</good_example>\n\n<bad_example>\nmorning_reflection: Market was somewhat mixed today with some positions performing better than expected.\nafternoon_plan: Continue holding current positions and watch for afternoon opportunities.\n<reasoning>\nBad: no specific prices, no ticker-level analysis, "somewhat mixed" is vague and unverifiable. Afternoon plan has no actionable content — no stops, no targets, no specific tickers. Could have been written without any tools. Zero information value.\n</reasoning>\n</bad_example>'
WHERE agent_key = 'midday'
AND system_prompt NOT LIKE '%FEW-SHOT EXAMPLES%';
