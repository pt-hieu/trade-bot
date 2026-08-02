-- Add strategy directive awareness to synthesis, midday, and retro prompts.
-- The actual directive text is injected at runtime via context_parts (synthesis)
-- and prompt building (midday, retro). This migration adds instructions about
-- how agents should USE the directive when present.

-- Synthesis: add directive compliance section
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## STRATEGY DIRECTIVE (HIGHEST PRIORITY)\nIf a STRATEGY DIRECTIVE section is present in your context, your brief MUST align with it:\n- TOP PICKS must come from sectors/tickers the directive focuses on\n- Avoid sectors the directive says to avoid\n- Position actions should follow directive guidance\n- Brief tone should match the directive''s risk stance (AGGRESSIVE/NEUTRAL/DEFENSIVE/CASH_PRESERVATION)\n- The DIRECTIVE CONSTRAINTS (budget, max entries, min R:R) are mandatory limits that override other rules\n- Reference the directive''s theme in MARKET MOOD section'
WHERE agent_key = 'synthesis';

-- Midday: add directive reference
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## STRATEGY DIRECTIVE AWARENESS\nIf a strategy directive is provided in context:\n- Assess whether the directive''s stance is playing out correctly\n- Note if market conditions have changed since morning that invalidate the directive\n- Afternoon plan should maintain or adjust the directive''s recommendations\n- Flag if any midday action contradicts the directive'
WHERE agent_key = 'midday';

-- Retro generator: add directive evaluation
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## STRATEGY DIRECTIVE EVALUATION\nIf a strategy directive was provided for today:\n- Evaluate whether the directive''s stance was correct given EOD outcomes\n- Did focus sectors outperform as directed?\n- Were avoided sectors correctly identified?\n- Was the key risk managed appropriately?\n- Include a DIRECTIVE ACCURACY section in the retrospective'
WHERE agent_key = 'retro_generator';
