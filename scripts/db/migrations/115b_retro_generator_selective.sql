-- Migration 115b: Fix retro_generator — prevent "suspend trading" recommendations
-- Part of migration 115 (the replace target string differed in DB vs JSON)

UPDATE agent_prompts SET system_prompt = replace(
  system_prompt,
  '- If actionable_rules data provided, use the strongest one as the rule',
  '- If actionable_rules data provided, use the strongest one as the rule
- NEVER recommend suspending trading or switching to pure capital preservation. Low win rate = raise the quality bar (stricter R:R, better entries, wider stops) -- NOT stop trading entirely.
- The cure for a losing streak is one well-structured winner, not inactivity.
- Rule changes must be QUALITY FILTERS (e.g., "Require R:R >= 4.0 when win rate < 35%"), never quantity caps ("stop trading until win rate improves").'
) WHERE agent_key = 'retro_generator';
