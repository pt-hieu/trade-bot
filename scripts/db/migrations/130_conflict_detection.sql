-- Migration 130: Add CONFLICT DETECTION (MANDATORY) to 4 agents
--
-- Adds to:
--   sector:       Cross-signal conflict enumeration before any BUY/AVOID signal
--   midday:       Morning vs midday data conflict protocol
--   market_level: Multi-source regime conflict enumeration
--   longterm:     Technical vs fundamental conflict before action recommendation
--
-- synthesis already has CONFLICT DETECTION from migration 111.
-- All UPDATEs are idempotent: guarded by NOT LIKE '%CONFLICT DETECTION%'

-- 1. sector: Conflict detection across all available technical signals
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONFLICT DETECTION (MANDATORY)\nBefore assigning a BUY or AVOID signal to any ticker:\n1. LIST all available signals: RSI zone, candlestick pattern, trend direction, MACD, volume, sector regime, flow data, insider activity\n2. For each conflict, state it explicitly in the note — e.g. "Conflict: RSI 35 (buy zone) but trend DOWNTREND and momentum bearish"\n3. Resolution priority: CRITICAL FILTERS (existing above) > trend/momentum > RSI zone > pattern > flow\n4. If 2+ major signals conflict with no clear resolution: downgrade BUY to WATCH with "conflicting signals" note\nFORBIDDEN: Assigning BUY when you have not explicitly checked for contradicting signals first.'
WHERE agent_key = 'sector'
AND system_prompt NOT LIKE '%CONFLICT DETECTION%';

-- 2. midday: Morning recommendation vs midday data conflict
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONFLICT DETECTION (MANDATORY)\nBefore writing afternoon_plan:\n1. For each morning recommendation or active holding, LIST any divergence between morning plan and midday reality\n2. State each conflict explicitly — e.g. "Conflict: morning BUY at 107k but midday low hit 105k (below stop at 106k)"\n3. Resolution priority: midday data > morning recommendation (newer information wins)\n4. If morning stance was AGGRESSIVE but midday shows broad index weakness: explicitly recommend stance adjustment\nFORBIDDEN: Confirming the morning plan without first checking whether midday data contradicts it.'
WHERE agent_key = 'midday'
AND system_prompt NOT LIKE '%CONFLICT DETECTION%';

-- 3. market_level: Cross-source regime conflict enumeration
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONFLICT DETECTION (MANDATORY)\nBefore classifying regime:\n1. LIST signals from each source: VN-Index technicals, sector rotation, news sentiment, foreign flow, historical patterns\n2. For each conflict, state it explicitly — e.g. "Conflict: RSI 62 bullish but foreign selling -500B VND net"\n3. Resolution priority: VN-Index technicals > sector rotation > foreign flow > news sentiment\n4. If 3+ sources conflict with no clear resolution: set regime_confidence <= 0.5 and note "conflicting signals across sources"\nFORBIDDEN: Stating regime with confidence > 0.7 when 2+ major sources contradict it.'
WHERE agent_key = 'market_level'
AND system_prompt NOT LIKE '%CONFLICT DETECTION%';

-- 4. longterm: Technical vs zone status conflict before action recommendation
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONFLICT DETECTION (MANDATORY)\nBefore recommending action for any ticker:\n1. LIST available signals: entry zone status (above/at/below), RSI zone, trend direction, conviction level, any research findings\n2. For each conflict, state it explicitly — e.g. "Conflict: BUY ZONE (price below entry) but RSI 22 in DOWNTREND with no reversal signal"\n3. Resolution priority: trend confirmation > entry zone status > RSI zone > conviction level\n4. BUY ZONE + DOWNTREND + no reversal pattern = "WATCH for reversal confirmation" (not immediate buy)\nFORBIDDEN: Recommending immediate accumulation when technical and zone signals contradict without naming the conflict.'
WHERE agent_key = 'longterm'
AND system_prompt NOT LIKE '%CONFLICT DETECTION%';
