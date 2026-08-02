-- Migration 311: persist zero-BUY streak alert on daily_records.
--
-- The streak detector (scripts/agents/retro/streak.py) writes a JSONB
-- blob here at retro close; the next morning brief reads it to render
-- the streak banner — single derivation path across live + resume.
--
-- Shape: {length: int, start_date: ISO date, gate_profile: str}
-- gate_profile ∈ {regime_gated, belief_flattening, rr_floor, mixed}

ALTER TABLE daily_records
    ADD COLUMN IF NOT EXISTS streak_alert_json JSONB;

COMMENT ON COLUMN daily_records.streak_alert_json IS
    'Zero-BUY streak alert produced by retro at scan close. Read by next '
    'morning brief to render the streak banner. NULL when no streak detected.';
