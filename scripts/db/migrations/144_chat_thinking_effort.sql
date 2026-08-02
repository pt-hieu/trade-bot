-- Migration 144: Add thinking_effort to chat_conversations
-- Type: DDL — requires owner connection URL

ALTER TABLE chat_conversations
  ADD COLUMN IF NOT EXISTS thinking_effort TEXT NOT NULL DEFAULT 'off';
