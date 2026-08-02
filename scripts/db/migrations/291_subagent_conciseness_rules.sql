-- Migration 291: Add OUTPUT LENGTH RULES to sub-agent prompts (sector_news, sector_technical, sector_enrichment, positions_thesis, positions_value, positions_technical)
-- Fixes: 96K token runaway in sector_news (infrastructure) and positions_thesis (2026-04-07)
-- Root cause: 8c3ac11 bounded aggregator output but missed sub-agent schemas where generation actually happens
-- Schema max_length enforces hard limits, prompt rules guide the model to stay concise

-- Sector sub-agents (news, technical, enrichment) — idempotent guard
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## OUTPUT LENGTH RULES (MANDATORY)\n- reasoning: max 2-3 sentences (what drives your signal, no preambles)\n- key_risk: max 1 sentence (the strongest counter-argument)\n- summary: max 2-3 sentences (sector-level theme)\n- belief_narrative: max 2 sentences (why this direction)\n- update_reason: max 1 sentence (what changed from prior belief)\nBe direct. No restating input data, no hedging paragraphs.\n',
    updated_at = NOW()
WHERE agent_key IN ('sector_news', 'sector_technical', 'sector_enrichment')
  AND system_prompt NOT LIKE '%OUTPUT LENGTH RULES%';

-- Positions sub-agents (thesis, value, technical) — idempotent guard
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## OUTPUT LENGTH RULES (MANDATORY)\n- reasoning: max 2-3 sentences (what drives your action recommendation)\n- counter_thesis: max 1 sentence (strongest argument against your action)\n- summary: max 2-3 sentences (portfolio-level overview)\n- belief_narrative: max 2 sentences (why this direction)\n- update_reason: max 1 sentence (what changed from prior belief)\nBe direct. No restating input data, no hedging paragraphs.\n',
    updated_at = NOW()
WHERE agent_key IN ('positions_thesis', 'positions_value', 'positions_technical')
  AND system_prompt NOT LIKE '%OUTPUT LENGTH RULES%';

-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/291_subagent_conciseness_rules.sql
