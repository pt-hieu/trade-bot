-- Migration 067: Retro feedback bootstrap
-- Fix: Backfill trading_rules from existing learning_patterns
-- Ensures tool_trading_rules, tool_winning_patterns, tool_losing_patterns return data
-- Root cause: insert_learnings.py unconditionally DELETE FROM learning_patterns
--             when retro produces 0 patterns → all historical data wiped

-- Backfill trading_rules from losing patterns with high loss rates (if any exist)
INSERT INTO trading_rules (rule_name, rule_type, description, action, confidence, sample_size, created_at)
SELECT
    LEFT(avoid_rule, 255) AS rule_name,
    'avoid' AS rule_type,
    avoid_rule AS description,
    'REDUCE_OR_SKIP' AS action,
    loss_rate AS confidence,
    sample_size,
    NOW() AS created_at
FROM learning_patterns
WHERE pattern_type = 'losing'
  AND loss_rate >= 0.7
  AND sample_size >= 1
  AND avoid_rule IS NOT NULL
  AND avoid_rule != ''
ON CONFLICT (rule_name) DO UPDATE
    SET confidence = EXCLUDED.confidence,
        sample_size = EXCLUDED.sample_size,
        updated_at = NOW()
WHERE trading_rules.confidence < EXCLUDED.confidence;

-- Add index to speed up retro constraint queries
CREATE INDEX IF NOT EXISTS idx_learning_patterns_type_loss
    ON learning_patterns(pattern_type, loss_rate, sample_size);
