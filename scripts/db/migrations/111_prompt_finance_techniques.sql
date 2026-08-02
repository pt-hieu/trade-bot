-- Migration 111: Apply research-backed finance prompting techniques
--
-- Adds to 5 agents:
--   synthesis:        CONFLICT DETECTION (mandatory signal conflict enumeration)
--   sector:           SIGNAL CONFIDENCE (calibrated HIGH/MEDIUM/LOW confidence tags)
--   entry_strategist: BULL/BEAR BALANCE (counter systematic bullish bias in KEY RISK)
--   retro_evaluator:  INSUFFICIENT DATA RULE (abstinence when data is missing/stale)
--   critic:           VERIFICATION PROTOCOL (cite data source for every issue flagged)
--
-- All UPDATEs are idempotent: guarded by NOT LIKE '%<section header>%'

-- 1. synthesis: Conflict detection protocol
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CONFLICT DETECTION (MANDATORY)\nBefore writing TOP PICKS or MY HOLDINGS actions:\n1. LIST conflicting signals per ticker across inputs (sector signal vs position alert vs regime vs flow)\n2. State each conflict explicitly in the note field: \"Conflict: sector BUY but regime RISK_OFF\"\n3. Resolution priority: regime > position guidance > sector signal > flow\n4. Unresolvable conflicts: downgrade to WATCH with \"conflicting signals\" note\nFORBIDDEN: Use of \"on balance\" or \"taking everything into account\" without first listing conflicts.'
WHERE agent_key = 'synthesis'
AND system_prompt NOT LIKE '%CONFLICT DETECTION%';

-- 2. sector: Signal confidence calibration
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## SIGNAL CONFIDENCE\nFor BUY and WATCH signals, append a confidence tag at the end of the note field:\n- [HIGH]:   RSI zone + candlestick pattern + volume confirmation + sector regime all align (4/4)\n- [MEDIUM]: 3 of 4 align, one minor conflict noted explicitly in the note\n- [LOW]:    Only 2 of 4 align — automatically downgrade BUY to WATCH\n\nIf you cannot cite 3+ data points from the provided tools supporting a BUY signal, it is a WATCH.\nExample note suffix: \"RSI 42 at support, hammer on 1.8x volume, banking HOT [HIGH]\"'
WHERE agent_key = 'sector'
AND system_prompt NOT LIKE '%SIGNAL CONFIDENCE%';

-- 3. entry_strategist: Bull/bear balance to counter LLM bullish bias
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## BULL/BEAR BALANCE\nKEY RISK must be the strongest counter-argument to today''s STANCE:\n- AGGRESSIVE stance: KEY RISK must argue for caution — what specific condition would invalidate this stance\n- DEFENSIVE stance: KEY RISK must name what opportunity you would miss if wrong\n- NEUTRAL stance: KEY RISK must present both a bear and bull scenario equally\n\nNever present KEY RISK as a minor footnote. It must genuinely challenge the thesis.\nLLMs systematically underweight downside scenarios in financial analysis — this section corrects that bias.\nA weak KEY RISK (e.g., \"market could be volatile\") is a flag for hallucinated confidence.'
WHERE agent_key = 'entry_strategist'
AND system_prompt NOT LIKE '%BULL/BEAR BALANCE%';

-- 4. retro_evaluator: Abstinence rule for missing/stale data
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## INSUFFICIENT DATA RULE\nIf price data for a ticker is missing, zero-valued, or cannot be verified:\n  analysis: "INSUFFICIENT DATA — [describe what is missing or unverifiable]"\n  error_type: "N/A"\n  lesson: ""\n\nDo NOT fabricate price comparisons, infer from memory, or extrapolate from other tickers.\nDo NOT generate analysis text when the underlying data is absent.\nA blank analysis entry is better than a wrong analysis entry.\nThis applies to: EOD prices, intraday high/low, entry prices, any field used in price comparison.'
WHERE agent_key = 'retro_evaluator'
AND system_prompt NOT LIKE '%INSUFFICIENT DATA RULE%';

-- 5. critic: Verification protocol — only flag what you can prove
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## VERIFICATION PROTOCOL\nFor each issue you flag, you MUST:\n1. Cite the specific section and exact claim (e.g., "TOP PICKS TCB: R:R stated as 3.2")\n2. State which pre-computed data or CONTEXT field contradicts it (e.g., "pre-computed setup shows R:R 2.8")\n3. If you cannot cite a specific data source for the contradiction: do NOT flag it as an issue\n\nFalse positives waste refiner iterations and degrade trust in the critic.\nOnly flag issues you can prove with data present in the CONTEXT or pre-computed sections.\nWhen uncertain between flagging and not flagging: default to NOT flagging.'
WHERE agent_key = 'critic'
AND system_prompt NOT LIKE '%VERIFICATION PROTOCOL%';
