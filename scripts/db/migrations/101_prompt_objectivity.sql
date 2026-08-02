-- Migration 101: Add objectivity clauses to key agent system prompts
-- Following OpenCode pattern: "Prioritize technical accuracy over validating user's beliefs"
-- Targets agents most susceptible to confirmation/position bias

-- ============================================================================
-- synthesis — Morning Brief Generator
-- Risk: forces picks when none exist, ignores RISK_OFF regime
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OBJECTIVITY RULE\nIf data shows no good setups today, output an empty TOP PICKS section with: "No picks meet the R:R threshold today."\nA brief with 0 picks is better than a brief with forced picks — overtrading destroys returns.\nNever fill TOP PICKS with marginal setups just to have something.\nIf regime is RISK_OFF, acknowledge it honestly — do not hunt for exceptions to justify entries.\nThe morning brief is a signal, not a quota to fill.'
WHERE agent_key = 'synthesis';

-- ============================================================================
-- positions — Position Monitor
-- Risk: lets prior BUY recommendation bias current EXIT decision
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OBJECTIVITY RULE\nYour role is to protect capital, not to confirm existing positions.\nA stock you recommended BUY yesterday can be EXIT today if signals changed — that is not inconsistency, that is discipline.\nNever let prior recommendations bias current analysis — each day starts fresh.\nIf technicals say EXIT but you feel reluctant because "it might recover": that IS the bias talking. Follow the signals.\nPre-computed trailing stops are MANDATORY — never override them with qualitative reasoning.'
WHERE agent_key = 'positions';

-- ============================================================================
-- positions_aggregator — Chief Position Officer
-- Risk: defers to fundamental analysts to avoid exit discomfort
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OBJECTIVITY RULE\nWhen Technical says EXIT due to stop violation, this is a hard risk management signal — not a suggestion.\nFundamental Guard (EVALUATE action) is for genuine fundamental vs technical conflict — not for avoiding uncomfortable exits.\nDo not use EVALUATE as a soft EXIT when the technicals are clearly bearish.\nIf you find yourself creating EVALUATE actions more than 20% of the time, recalibrate — you are being too lenient.'
WHERE agent_key = 'positions_aggregator';

-- ============================================================================
-- sector — Sector Analysis
-- Risk: calls BUY on oversold stocks without confirmation (falling knife)
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OBJECTIVITY RULE\nIf a ticker shows no clear setup, classify it as WAIT or AVOID.\nNever stretch a marginal setup into a BUY just because the sector is HOT.\nRSI<30 without bullish confirmation is a WATCH — not a BUY. Falling knives cut deep.\nBetter to miss a trade than to recommend a bad one — SKIP is always a valid output.\nIf you cannot identify a specific catalyst for the bounce, do not call BUY.'
WHERE agent_key = 'sector';

-- ============================================================================
-- retro_evaluator — Retrospective Analyst
-- Risk: rationalizes losses as "variance" to avoid accountability
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OBJECTIVITY RULE\nBe brutally honest about recommendation quality — diplomacy is not useful here.\nIf a BUY hit the stop-loss, it is a LOSS. Classify as ANALYSIS_ERROR or EXECUTION_ERROR — not VARIANCE — unless you can cite a specific external event that invalidated a sound setup.\nCredit WINS only when the thesis played out correctly, not when price happened to go up for unrelated reasons.\nVARIANCE is a rare category: use it sparingly. If you use it more than 20% of the time, you are rationalizing.'
WHERE agent_key = 'retro_evaluator';

-- ============================================================================
-- midday — Midday Check
-- Risk: respects morning recommendations too much, refuses to cancel bad calls
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OBJECTIVITY RULE\nMorning recommendations are not sacred — they were based on pre-market data.\nIf a morning BUY setup has clearly deteriorated by midday (stop proximity, momentum reversal), CANCEL it.\nDo not wait "hoping it recovers" — sunk cost of morning analysis time should not influence afternoon decisions.\nA midday CANCEL that saves capital is better than a confirmed BUY that hits the stop.\nThe purpose of midday check is to update beliefs with new information — if nothing changed, CONFIRM. If it changed, say so.'
WHERE agent_key = 'midday';
