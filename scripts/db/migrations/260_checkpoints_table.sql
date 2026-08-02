-- Checkpoint system for tracking before/after metrics when pipeline changes are deployed.
-- Solves the rolling window contamination problem: baseline and evaluation metrics
-- are computed on-demand from daily_records using date boundaries, not stored as snapshots.

CREATE TABLE IF NOT EXISTS checkpoints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'active', 'completed')),

  -- Timing
  deployed_at TIMESTAMPTZ,
  baseline_window_days INT NOT NULL DEFAULT 14,
  evaluation_days INT NOT NULL DEFAULT 14,
  evaluation_ends TIMESTAMPTZ,

  -- What you expect to change
  target_metrics TEXT[] NOT NULL DEFAULT '{}',
  expected_direction JSONB NOT NULL DEFAULT '{}',

  -- Links to pipeline components
  affected_agents TEXT[] DEFAULT '{}',
  git_commit TEXT,

  -- Result (set when status -> completed)
  verdict TEXT CHECK (verdict IN ('improved', 'mixed', 'no_change', 'degraded')),
  result JSONB,

  created_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_status ON checkpoints(status);
CREATE INDEX IF NOT EXISTS idx_checkpoints_deployed ON checkpoints(deployed_at);
