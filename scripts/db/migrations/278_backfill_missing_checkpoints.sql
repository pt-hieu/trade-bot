-- Migration 278: Backfill 3 checkpoints accidentally created in local DB only
-- Type: DML (default connection works)
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/278_backfill_missing_checkpoints.sql
--
-- Context: create_checkpoint calls in Apr 1 sessions hit local DB instead of Neon.
-- After running this, truncate local checkpoints table manually.

INSERT INTO checkpoints (id, name, description, status, deployed_at, baseline_window_days, evaluation_days, evaluation_ends, target_metrics, expected_direction, affected_agents, git_commit, created_at)
VALUES
(
    '6d005063-b7c9-4cec-ace8-085681cf1574',
    'International RSS feed ingestion',
    'Added 7 international RSS feeds (CNBC, MarketWatch, OilPrice, Fed, ECB, Nikkei Asia, VnExpress Intl) to news pipeline. Articles flow through blocklist, macro-keyword allowlist, age filter, title dedup, and LLM scoring into existing catalyst/event discovery. Expanded English sentiment keywords and ticker false positives for intl article handling.',
    'active',
    '2026-04-01T16:41:14.912894+00:00',
    14, 14,
    '2026-04-15T16:41:14.912894+00:00',
    ARRAY['win_rate','signal.entry_accuracy','macro.overall_accuracy'],
    '{"win_rate": "up", "signal.entry_accuracy": "up", "macro.overall_accuracy": "up"}',
    ARRAY['news_examiner','catalysts','capital_events','macro'],
    'd9616c5',
    '2026-04-01T16:41:15.038278+00:00'
),
(
    'd49d5007-5471-40df-8544-38126d03983f',
    'Centralize constraints + fix on_track',
    'on_track now uses progress-vs-pace (was always True). Urgency ladder enabled. Composed min_rr/max_picks wired to picks + validator (was hardcoded 3.0/5). Expect tighter constraints for behind-pace goals, slightly looser for composed values vs raw goal urgency.',
    'active',
    '2026-04-01T16:06:52.576969+00:00',
    14, 14,
    '2026-04-15T16:06:52.576969+00:00',
    ARRAY['win_rate','entry_hit_rate','signal.BUY_accuracy'],
    '{"win_rate": "up", "entry_hit_rate": "up", "signal.BUY_accuracy": "up"}',
    ARRAY['entry_strategist','retro_evaluator'],
    '7c8bdaf',
    '2026-04-01T16:06:52.622458+00:00'
),
(
    '9ee6bf54-0797-4813-8df2-ade6023ebf2b',
    'Geo shock centralization + date parsing fix',
    'Centralized geopolitical phase config into shared/rules/geopolitical.py. Fixed silent date parsing failure for month-only open-ended periods. Eliminated TS phase re-resolution. Added resolution_or_escalation phase to agent context (0.9x multiplier). Added CAUTIOUS calibration ceiling. Persisted resolved shock to macro_metrics JSONB column.',
    'active',
    '2026-04-01T15:16:40.585434+00:00',
    14, 14,
    '2026-04-15T15:16:40.585434+00:00',
    ARRAY['win_rate','signal.exit_accuracy','macro.overall_accuracy'],
    '{"win_rate": "up", "signal.exit_accuracy": "up", "macro.overall_accuracy": "up"}',
    ARRAY['entry_strategist','synthesis','midday','macro'],
    'pending',
    '2026-04-01T15:16:40.640231+00:00'
)
ON CONFLICT (id) DO NOTHING;
