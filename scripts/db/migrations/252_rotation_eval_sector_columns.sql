-- Add hot_sectors/cold_sectors JSONB columns to rotation_evaluations
-- so load_learnings_from_db() can reconstruct the full eval dict
ALTER TABLE rotation_evaluations
  ADD COLUMN IF NOT EXISTS hot_sectors JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS cold_sectors JSONB DEFAULT '[]';
