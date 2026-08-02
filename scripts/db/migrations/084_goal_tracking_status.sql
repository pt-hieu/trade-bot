-- Add 'Tracking' goal status
-- Goals with this status sync realized_vnd (like Active) but are excluded from the pipeline
-- Use case: track progress of a paused/background goal without influencing the morning brief

ALTER TYPE goal_status ADD VALUE IF NOT EXISTS 'Tracking';
