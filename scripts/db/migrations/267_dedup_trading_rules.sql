-- Migration 267: Clean up duplicate avoid rules from percentage-drift bug
--
-- Bug: rule_name was the full avoid_rule text including "failing at X%", so each
-- retro run with a slightly different loss percentage created a NEW row instead
-- of upserting. Fix: delete all avoid rules — they are re-derived from the rolling
-- window on every retro run (daily). Next run recreates with stable keys.

DELETE FROM trading_rules WHERE rule_type = 'avoid';
