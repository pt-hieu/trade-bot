-- Migration 105: Set max_tokens=10000 for longterm_review agent
-- Prevents output truncation when reviewing batches of ~5 stocks at ~2,500-3,000 tokens each.

UPDATE agent_prompts SET max_tokens = 10000 WHERE agent_key = 'longterm_review';
