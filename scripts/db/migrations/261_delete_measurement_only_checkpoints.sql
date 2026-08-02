-- Delete backfilled checkpoints that fixed measurement/storage, not pipeline behavior.
-- These compared metrics computed with broken ruler vs fixed ruler — apples to oranges.
DELETE FROM checkpoints
WHERE git_commit IN (
  'b07a8e7',  -- Wire update_learnings + fix won logic (fixed how wins were determined, not behavior)
  'af9ab20',  -- Fix 8 regime detection bugs (fixed regime eval, not regime detection)
  'ffa9a71',  -- Correct TRIM/EXIT evaluation using prev_close (fixed eval metric, not signal generation)
  '9183b4e',  -- Fix numpy serialization + gap-down blindness (serialization fix)
  '8955d5b',  -- Fix k-VND unit mismatch in retro compute (unit conversion in measurement)
  '5e9da1d',  -- Persist calibration fields to daily_evaluations (storage fix, no behavior change)
  '9338223',  -- Fix 6 retro pipeline bugs (eval/pattern extraction fixes)
  'b7171c4',  -- Exclude MISSED from win_rate denominator (metric definition change)
  '5ec4057',  -- Fix 0% win_rate streak + historical data quality (measurement bug)
  'c18c622',  -- Fix regime accuracy + tighten thresholds (eval logic fix)
  'b79fede'   -- Fix asyncpg SQL bug killing macro_metrics (storage bug)
);
