-- Migration 222: Add unique constraint on agent_beliefs to prevent duplicate insertions
-- DDL migration — needs owner connection

-- Step 1: Delete existing duplicates (keep first per group via row_number)
DELETE FROM agent_beliefs
WHERE id IN (
  SELECT id FROM (
    SELECT id, ROW_NUMBER() OVER (
      PARTITION BY record_date, ticker, agent_key, ensemble_type
      ORDER BY created_at ASC
    ) AS row_num
    FROM agent_beliefs
  ) ranked
  WHERE ranked.row_num > 1
);

-- Step 2: Create unique index (idempotent)
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_beliefs_unique
  ON agent_beliefs(record_date, ticker, agent_key, ensemble_type);
