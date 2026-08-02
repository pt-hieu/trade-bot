-- Experiment checkpoint: held tickers missing technicals + midday guardrails
-- Already applied to production via SSH (id: 36bbb54e-8157-4d4c-9f44-ee21e04bde10)
INSERT INTO checkpoints (name, description, target_metrics, expected_direction, affected_agents, git_commit, status, deployed_at)
VALUES (
  'Fix held tickers missing technicals + midday guardrails',
  'Root cause: held tickers deactivated from swing_watchlist had no technicals fetched',
  ARRAY['entry_hit_rate', 'midday.adjustment_win_rate', 'signal.ADD_accuracy'],
  '{"entry_hit_rate": "up", "midday.adjustment_win_rate": "up", "signal.ADD_accuracy": "up"}'::jsonb,
  ARRAY['midday', 'positions_technical', 'positions_ensemble_aggregator'],
  'pending',
  'active',
  NOW()
)
ON CONFLICT DO NOTHING;
