-- Migration 268: Deactivate refiner agent (code deleted, config still active)
-- refiner.py was removed when Critic became 1-pass (no rewrite).
-- Per CLAUDE.md rule 12: no backward compatibility shims — dead code gets deleted.

UPDATE agent_prompts SET is_active = false WHERE agent_key = 'refiner';
