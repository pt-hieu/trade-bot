-- Agent prompts: store PydanticAI agent system prompts in DB
-- Enables viewing/editing via web app + version history

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS agent_prompts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  agent_key VARCHAR(50) NOT NULL UNIQUE,
  agent_name VARCHAR(100) NOT NULL,
  description TEXT,
  system_prompt TEXT NOT NULL,
  model_tier VARCHAR(20) DEFAULT 'heavy',
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_prompt_versions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  prompt_id UUID NOT NULL REFERENCES agent_prompts(id) ON DELETE CASCADE,
  version_number INT NOT NULL,
  system_prompt TEXT NOT NULL,
  change_note TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(prompt_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_prompt_versions_prompt_id
  ON agent_prompt_versions(prompt_id);
