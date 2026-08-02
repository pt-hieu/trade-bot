-- Set low temperature for structured output / parsing agents
-- These agents extract data deterministically — high temperature causes inconsistent results
UPDATE agent_prompts SET temperature = 0.2
WHERE agent_key IN ('retro_parser', 'sector_aggregator', 'positions_aggregator', 'alert_registrar')
  AND (temperature IS NULL OR temperature > 0.2);
