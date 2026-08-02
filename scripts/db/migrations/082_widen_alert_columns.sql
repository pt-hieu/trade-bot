-- Migration 082: Widen short VARCHAR columns in morning_position_alerts
-- volume_signal: agent outputs can be longer than 50 chars
-- consensus: longer consensus strings possible
ALTER TABLE morning_position_alerts ALTER COLUMN volume_signal TYPE VARCHAR(200);
ALTER TABLE morning_position_alerts ALTER COLUMN consensus TYPE VARCHAR(100);
ALTER TABLE morning_position_alerts ALTER COLUMN action TYPE VARCHAR(20);
