-- Migration 148: Relax retro constraint thresholds and position scaling floor
-- Problem: Current thresholds trigger too aggressively, compounding with goal urgency
-- to create complete trading paralysis.
--
-- Changes:
--   retro_severe_winrate: 35% → 25%  (35% is normal for many profitable swing systems)
--   retro_moderate_winrate: 45% → 35%
--   retro_severe_max_entries: 1 → 2   (never lock to single entry)
--   retro_severe_min_rr: 4.0 → 3.5   (achievable for VN stocks)
--   retro_severe_scale: 0.500 → 0.750 (less punishing - tiny positions can't recover P/L)
--   retro_moderate_max_entries: 2 → 3
--   retro_moderate_min_rr: 3.5 → 3.0  (base R:R floor)
--   minimal_scale_factor: 0.25 → 0.50  (floor at 50% — 25% positions are meaningless)

UPDATE trading_config SET
  retro_severe_winrate     = 25.0,
  retro_moderate_winrate   = 35.0,
  retro_severe_max_entries = 2,
  retro_severe_min_rr      = 3.5,
  retro_severe_scale       = 0.750,
  retro_moderate_max_entries = 3,
  retro_moderate_min_rr    = 3.0,
  minimal_scale_factor     = 0.500,
  updated_at               = NOW()
WHERE id = 1;
