-- Deactivate retro_patterns agent — replaced by deterministic Python in patterns.py
UPDATE agent_prompts SET is_active = FALSE WHERE agent_key = 'retro_patterns';
