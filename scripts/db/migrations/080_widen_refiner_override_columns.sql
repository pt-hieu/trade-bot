-- Migration 080: Widen refiner_overrides VARCHAR columns
-- original_action and override_action were VARCHAR(50), too short for compound values
ALTER TABLE refiner_overrides ALTER COLUMN original_action TYPE VARCHAR(100);
ALTER TABLE refiner_overrides ALTER COLUMN override_action TYPE VARCHAR(100);
