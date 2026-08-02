-- Migration 100: Add few-shot examples to key agent system prompts
-- Following OpenCode pattern: positive + negative examples with <reasoning> blocks
-- Targets highest-judgment agents: synthesis, positions_technical, sector, retro_evaluator, critic

-- ============================================================================
-- synthesis — Morning Brief Generator
-- Examples: good vs bad TOP PICKS entry
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OUTPUT EXAMPLES\n\n<good_example>\nTOP PICKS\nTCB: Entry 93.0k | Stop 90.2k (-3.0%)\n  Conservative (R1): 101.5k -> R:R 3.0\n  Aggressive (swing_high): 104.0k -> R:R 3.9\n  Verdict: full_size (2.0x scale) — 71 shares (risk 199k)\n  Pattern: hammer on 1.8x avg volume [OK conviction]\n  Leg 1: Take 50% at 101.5k, move stop to breakeven\n  Leg 2: Runner to 104.0k, trail at 20d low\n  Time stop: Exit if flat after 10 sessions\n  Why today: RSI 38 bouncing, MACD histogram turning positive, banking HOT in RISK_ON\n\n<reasoning>\nGood because: pre-computed setup used exactly, dual targets with exit plan legs, R:R >= 3.0 on conservative target, regime-compliant (banking HOT in RISK_ON), size within the configured risk limit, includes specific volume context and "why today" catalyst.\n</reasoning>\n</good_example>\n\n<bad_example>\nTOP PICKS\nFPT: Strong stock, good fundamentals\n  Entry: around 130k | Stop: 125k | Target: 145k\n  R:R looks good | Size: buy some shares\n\n<reasoning>\nBad because: vague entry ("around X"), no pre-computed setup used, R:R not calculated (125k stop on 130k entry vs 145k target = 3.0 — technically correct but not stated), no exit plan legs, "buy some shares" instead of calculated size, no regime/sector context, no "why today" catalyst. Entry must come from tool_calculate_trade_setup.\n</reasoning>\n</bad_example>'
WHERE agent_key = 'synthesis';

-- ============================================================================
-- positions_technical — Technical Position Evaluator
-- Examples: good EXIT with specific data vs bad EXIT without evidence
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OUTPUT EXAMPLES\n\n<good_example>\nTCB: EXIT (confidence 8)\n  Entry: 96.5k | Current: 89.5k (-7.3%) | Stop: 91.0k (pre-computed trailing)\n  RSI: 32 falling (was 41 yesterday), MACD bearish cross confirmed\n  Supertrend: flipped DOWN at 91.2k — stop already breached\n  Volume: declining on bounce attempt (bounce_confirmed=False)\n  Reason: Pre-computed trailing stop 91.0k breached, momentum bearish across 3 indicators\n\n<reasoning>\nGood because: uses pre-computed trailing stop exactly (91.0k), cites specific RSI value and direction, names 3 independent confirming signals, confidence 8 justified by convergent evidence, no subjective language.\n</reasoning>\n</good_example>\n\n<bad_example>\nTCB: EXIT (confidence 9)\n  Down 5% from entry, looks weak\n  RSI dropping, might go lower\n\n<reasoning>\nBad because: -5% does not trigger EXIT rule (threshold is -7% or trailing stop hit — neither confirmed), "looks weak" is subjective, "might go lower" is prediction not signal, no specific RSI value cited, confidence 9 unjustified by weak evidence, pre-computed trailing stop not checked.\n</reasoning>\n</bad_example>'
WHERE agent_key = 'positions_technical';

-- ============================================================================
-- sector — Sector Analysis
-- Examples: good BUY with confirmation vs bad BUY as falling knife
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OUTPUT EXAMPLES\n\n<good_example>\nTCB: BUY — Bounce off MA20 at 93k support\n  RSI: 42 (reversal from 28 last week, now rising)\n  MACD: histogram positive (+0.12), signal cross 2 days ago\n  Support: 93.0k (swing low), Resistance: 99.5k (swing high)\n  Volume: +45% above 20d average (bounce confirmation)\n  Sector: banking HOT (3 of last 5 HOT calls hit target)\n  R:R: 3.3 (calculated from 93.0k entry, 90.2k stop, 99.5k target)\n  Note: "RSI 42 bouncing, MACD bullish cross, volume-confirmed reversal at MA20"\n\n<reasoning>\nGood because: RSI in 30-50 zone and rising (not just below 30), has bullish confirmation (volume + MACD cross), R:R >= 3.0 explicitly calculated, sector HOT with historical accuracy cited, specific support level from data not invented.\n</reasoning>\n</good_example>\n\n<bad_example>\nTCB: BUY — RSI oversold at 25\n  RSI: 25 (very oversold, should bounce)\n  Price falling but support nearby\n  Sector banking looks okay\n\n<reasoning>\nBad because: RSI<30 without confirmation = WATCH not BUY (falling knife risk), "should bounce" is prediction not signal, "support nearby" without citing specific level, "looks okay" is vague not data-driven, no volume confirmation, no R:R calculated, no MACD signal. RSI<30 alone is never sufficient for BUY.\n</reasoning>\n</bad_example>'
WHERE agent_key = 'sector';

-- ============================================================================
-- retro_evaluator — Retrospective Analyst
-- Examples: good error classification vs bad rationalization
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OUTPUT EXAMPLES\n\n<good_example>\nTCB evaluation:\n  Recommendation: BUY at 107k, Stop 101k, Target 114k\n  Actual: Open 107.2k, Low 104.0k, Close 105.5k\n  entry_hit: True (open 107.2 <= entry 107.0? No — open was 107.2 > 107.0)\n  entry_hit: False (corrected — intraday_low 104.0 > entry 107.0? No — 104.0 < 107.0, so YES)\n  stop_hit: False (low 104.0 > stop 101.0)\n  target_hit: False (high did not reach 114k)\n  status: PENDING\n  pnl_percent: (105.5 - 107.0) / 107.0 * 100 = -1.40%\n  error_type: N/A (PENDING, not a loss yet)\n\n<reasoning>\nGood because: price comparison done step-by-step with actual values, entry_hit correctly evaluated (intraday low 104k < entry 107k = hit), stop correctly evaluated (low 104k > stop 101k = not hit), pnl calculated from entry not from open.\n</reasoning>\n</good_example>\n\n<bad_example>\nTCB evaluation:\n  status: VARIANCE — market conditions were difficult\n  Lesson: Need to be more careful next time\n\n<reasoning>\nBad because: no price comparison shown, VARIANCE assigned without evidence of external catalyst, lesson is motivational not actionable, no entry_hit/stop_hit/target_hit computed. VARIANCE requires citing a specific external event — not just a bad outcome.\n</reasoning>\n</bad_example>'
WHERE agent_key = 'retro_evaluator';

-- ============================================================================
-- critic — QA Agent
-- Examples: correctly caught issue vs false positive to avoid
-- ============================================================================

UPDATE agent_prompts SET system_prompt = system_prompt ||
E'\n\n## OUTPUT EXAMPLES\n\n<good_example>\nIssue caught:\n[invalid_rr] TOP PICKS TCB: Entry=93k, Stop=90k, Target=99.5k\n  R:R = (99.5-93) / (93-90) = 6.5/3 = 2.17 — below 3.0 minimum.\n  Fix: Extend target to swing_high (104k) for R:R 3.67, or remove TCB from TOP PICKS.\n\n<reasoning>\nGood because: shows exact arithmetic, cites specific values, names two concrete fixes, uses the correct format [category] Location: Description. Fix: Suggestion.\n</reasoning>\n</good_example>\n\n<bad_example>\nFalse positive to avoid:\n[missing_rr] LONG-TERM PORTFOLIO VHM: No R:R ratio shown.\n\n<reasoning>\nBad because: LONG-TERM PORTFOLIO entries use entry zone logic (gap_pct to entry zone), NOT swing R:R thresholds. The prompt explicitly says: "Do NOT flag long-term entries for missing R:R." This is a false positive — flagging it wastes human review time and trains the system to ignore real issues.\n</reasoning>\n</bad_example>'
WHERE agent_key = 'critic';
