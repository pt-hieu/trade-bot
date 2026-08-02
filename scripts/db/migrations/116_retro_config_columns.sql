-- Migration 116: Add retro constraint thresholds to trading_config
-- These values were previously hardcoded in retro_constraints.py.
-- Now configurable from the /config web UI.

ALTER TABLE trading_config
  ADD COLUMN IF NOT EXISTS retro_severe_winrate   NUMERIC(5,2) NOT NULL DEFAULT 35.0,
  ADD COLUMN IF NOT EXISTS retro_moderate_winrate NUMERIC(5,2) NOT NULL DEFAULT 45.0,
  ADD COLUMN IF NOT EXISTS retro_severe_max_entries  SMALLINT NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS retro_severe_min_rr       NUMERIC(4,1) NOT NULL DEFAULT 4.0,
  ADD COLUMN IF NOT EXISTS retro_severe_scale        NUMERIC(4,3) NOT NULL DEFAULT 0.500,
  ADD COLUMN IF NOT EXISTS retro_moderate_max_entries SMALLINT NOT NULL DEFAULT 2,
  ADD COLUMN IF NOT EXISTS retro_moderate_min_rr      NUMERIC(4,1) NOT NULL DEFAULT 3.5;
