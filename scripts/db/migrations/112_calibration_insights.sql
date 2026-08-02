-- Migration 112: Add calibration_insights table and update retro_evaluator with CALIBRATION_ERROR type
--
-- Problem: Learning system fixated on "execution failures" because:
-- 1. WAIT/WATCH/AVOID counted in win/loss stats (fixed in Python)
-- 2. No error type for quantitative miscalibration (stop too tight vs ATR, entry unreachable)
-- 3. "favor exits" feedback loop when win rate < 40%
--
-- This migration: adds calibration tracking table + updates evaluator prompt

-- ============================================================
-- 1. Calibration insights table (quantitative feedback loop)
-- ============================================================
CREATE TABLE IF NOT EXISTS calibration_insights (
    id SERIAL PRIMARY KEY,
    scan_date DATE NOT NULL DEFAULT CURRENT_DATE,
    avg_entry_gap_pct NUMERIC(6,2),        -- how far entry from actual day low (positive = reachable)
    pct_entries_unreachable NUMERIC(5,1),  -- % of entries where price never reached entry
    avg_stop_vs_atr NUMERIC(6,2),          -- avg stop_buffer / ATR ratio (< 1.0 = too tight)
    pct_stops_too_tight NUMERIC(5,1),      -- % of entries with stop/ATR < 1.0
    avg_predicted_rr NUMERIC(6,2),         -- avg (target-entry)/(entry-stop) we recommended
    avg_actual_rr NUMERIC(6,2),            -- avg (day_high-entry)/(entry-day_low) actually available
    target_hit_rate NUMERIC(5,1),          -- % of entered positions that hit target
    sample_size INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_calibration_date ON calibration_insights(scan_date);
COMMENT ON TABLE calibration_insights IS 'Quantitative calibration stats from retro pipeline (entry precision, stop adequacy, R:R accuracy)';

-- ============================================================
-- 2. Update retro_evaluator prompt: add CALIBRATION_ERROR type
-- ============================================================
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    '- **EXECUTION_ERROR**: Direction was correct but stop/timing/sizing was wrong
  - Evidence: direction_correct=True AND stop_hit=True → stop was too tight
  - Evidence: direction_correct=True AND status=MISSED → entry too aggressive
  - Example: "Stock went up after stopping us out — stop buffer was only 1.2%"

- **VARIANCE**: Setup was sound but market didn''t cooperate — random adverse day
  - Evidence: direction_correct=True, no structural issues, external catalyst
  - Example: "Valid setup, broad market selloff killed the move"

- **N/A**: WIN or EXCLUDED (SKIP/AVOID/WAIT/WATCH) tickers

For ANALYSIS_ERROR and EXECUTION_ERROR, add a one-line lesson:
- Lesson should be concrete and actionable, not motivational
- Good: "Stop too tight at 1.2% — need at least 2x ATR buffer"
- Bad: "Need to be more careful next time"

The evaluation hints provide: direction_correct=True/False and stop_buffer=X%
Use these as evidence for your classification.',
    '- **EXECUTION_ERROR**: Actual execution failure — did not place order, held past target, failed to follow plan mechanically
  - Evidence: direction_correct=True but no record of trade execution
  - Example: "Target hit at 110k but no exit executed — held and gave back gains"

- **CALIBRATION_ERROR**: Entry/stop/target levels were quantitatively miscalibrated
  - Evidence: entry_gap < 0 (entry unreachable — price never got there)
  - Evidence: stop/ATR < 1.0 (stop buffer tighter than one ATR — stops out on noise)
  - Evidence: direction_correct=True AND status=MISSED AND entry_gap > 1% (entry set too far)
  - Example: "Entry at 93k but day low was 94.5k [entry_gap=-1.6%] — entry unreachable, needed 95k"
  - Example: "Stop at 1.2% vs ATR 2.5% [stop/ATR=0.48] — sub-1-ATR stop, guaranteed noise stop-out"

- **VARIANCE**: Setup was sound but market did not cooperate — random adverse day
  - Evidence: direction_correct=True, no structural issues, external macro catalyst
  - Example: "Valid setup, broad market selloff on macro news killed the move"

- **N/A**: WIN or EXCLUDED (SKIP/AVOID/WAIT/WATCH) tickers

## OUTPUT CONSTRAINTS
- analysis field: max 2 sentences. Cite the specific hint that drove your classification.
- lesson field: max 1 sentence. Must include a specific number if actionable.
  Good: "Widen stop to >= 2.0% (1.5x ATR) [stop/ATR was 0.48]"
  Bad: "Be more careful with stops"

## DATA CITATION FOR CALIBRATION
For CALIBRATION_ERROR, always cite the calibration hints in analysis:
- Format: "stop 1.2% vs ATR 2.5% [stop/ATR=0.48]" or "entry 93k unreachable [entry_gap=-1.6%]"
- Do NOT classify as CALIBRATION_ERROR without citing a specific hint value.

## FEW-SHOT EXAMPLES

<good_example>
VHM BUY: Entry at 93,000 unreachable [entry_gap=-1.6%, day low 94,500]. Stop 1.2% sub-1-ATR [stop/ATR=0.48].
error_type: CALIBRATION_ERROR
lesson: Set entry at 94,800 (within 1% of support), stop >= 2.5% (1 ATR)
</good_example>

<bad_example>
VHM BUY: Direction was correct but we missed the entry.
error_type: EXECUTION_ERROR
lesson: Should have entered earlier.
Bad because: Misclassifies calibration failure as execution failure. No hint values cited. Lesson has no number.
</bad_example>

<good_example>
TCB BUY: Direction correct [direction=correct], stop at 1.3% hit before reversal [stop/ATR=0.52]. Price recovered +3% after stop.
error_type: CALIBRATION_ERROR
lesson: Minimum stop buffer 2x ATR = 2.5% for TCB
</good_example>

For ANALYSIS_ERROR and EXECUTION_ERROR, add a one-line lesson:
- Lesson must be concrete and include a specific number or threshold.

The evaluation hints provide: direction_correct, stop_buffer%, stop/ATR ratio, entry_gap%, pred_rr
Use ALL available hints as evidence for your classification.'
)
WHERE agent_key = 'retro_evaluator'
AND system_prompt LIKE '%EXECUTION_ERROR%'
AND system_prompt NOT LIKE '%CALIBRATION_ERROR%';
