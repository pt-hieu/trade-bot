-- Migration 113: Update retro_generator and entry_strategist prompts
--
-- Changes:
-- 1. retro_generator: Remove exit bias feedback loop, add CALIBRATION_ERROR to MISSES, add CALIBRATION CHECK section
-- 2. entry_strategist: Add calibration self-check (tool_get_learnings(query="calibration"))

-- ============================================================
-- 1. Update retro_generator: remove exit bias, add calibration
-- ============================================================

-- Remove the exit-bias feedback loop line
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'\n- If overall win rate < 40%: add "Bias: Favor exits over new entries until win rate recovers"',
    ''
)
WHERE agent_key = 'retro_generator'
AND system_prompt LIKE '%overall win rate < 40%: add%';

-- Add CALIBRATION_ERROR example to MISSES section
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '  Example: [VARIANCE] VCB BUY: Valid setup, broad market selloff on macro news. No fix needed.',
    E'  Example: [VARIANCE] VCB BUY: Valid setup, broad market selloff on macro news. No fix needed.\n  Example: [CALIBRATION_ERROR] VHM BUY: Entry 93k unreachable [entry_gap=-1.6%, low=94.5k]. Stop 1.2% sub-1-ATR [stop/ATR=0.48]. Lesson: Entry 94.8k, stop 2.5%'
)
WHERE agent_key = 'retro_generator'
AND system_prompt LIKE '%VARIANCE%VCB BUY%'
AND system_prompt NOT LIKE '%CALIBRATION_ERROR%';

-- Add CALIBRATION CHECK section after PATTERN UPDATE, before TOMORROW'S EDGE
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'\nTOMORROW''S EDGE\n- One concrete rule change',
    E'\nCALIBRATION CHECK (only if calibration_insights data provided)\n- Entry precision: {pct_entries_unreachable}% unreachable, avg gap {avg_entry_gap_pct}% [calibration_insights]\n- Stop adequacy: {pct_stops_too_tight}% too tight vs ATR, avg ratio {avg_stop_vs_atr} [calibration_insights]\n- R:R accuracy: predicted {avg_predicted_rr}:1 vs actual {avg_actual_rr}:1 [calibration_insights]\n- Target hit rate: {target_hit_rate}% [calibration_insights]\n- If calibration data provided: add one calibration fix to TOMORROW''S EDGE with a specific number\n  Good: "Rule: Widen stops from 1.2% to >= 2.0% (1.5x ATR). Evidence: 60% stops < 1 ATR, n=12"\n  Bad: "Rule: Use wider stops"\n\nTOMORROW''S EDGE\n- One concrete rule change'
)
WHERE agent_key = 'retro_generator'
AND system_prompt LIKE '%TOMORROW%S EDGE%'
AND system_prompt NOT LIKE '%CALIBRATION CHECK%';

-- ============================================================
-- 2. Update entry_strategist: add calibration self-check
-- ============================================================

UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## CALIBRATION SELF-CHECK\nBefore writing entry recommendations, call tool_get_learnings(query="calibration") to get recent calibration stats.\n\nApply these deterministic adjustments if calibration data is available:\n- pct_stops_too_tight > 50%: Set all stops >= 1.5x ATR for this session [calibration_insights.pct_stops_too_tight]\n- pct_entries_unreachable > 60%: Set entries within 1% of recent support, not mid-range [calibration_insights.pct_entries_unreachable]\n- avg_predicted_rr < 2.0: Only recommend setups with > 3:1 R:R [calibration_insights.avg_predicted_rr]\n\nIf calibration data unavailable: note "INSUFFICIENT DATA -- calibration stats not available" and proceed with standard parameters.'
WHERE agent_key = 'entry_strategist'
AND system_prompt NOT LIKE '%CALIBRATION SELF-CHECK%';
