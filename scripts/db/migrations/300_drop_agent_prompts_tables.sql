-- Migration 300: Drop agent_prompts and agent_prompt_versions tables.
--
-- Agent config now lives in YAML files (scripts/agents/configs/).
-- Nothing reads from these tables anymore — pipeline loads from YAML,
-- web admin graph is fully static.
--
-- DDL — requires owner connection.

DROP TABLE IF EXISTS agent_prompt_versions;
DROP TABLE IF EXISTS agent_prompts;
