-- Legalize columns that live in production but were never shipped via a
-- migration file. Background: the 2026-04-21 cascade exposed that the
-- migrations directory + schema.sql together didn't describe the real
-- schema — columns had been added directly (via psql / Neon console)
-- without an accompanying `.sql` file. This left the new schema-drift
-- pre-commit hook with ~100 false positives on day one.
--
-- Every ALTER below was verified against live Neon state on 2026-04-21
-- via `describe_table_schema`. All use IF NOT EXISTS so the migration is
-- safe to re-run and safe on fresh local Postgres bootstrapped from
-- scripts/db/schema.sql (which also contains these columns going forward).

BEGIN;

-- ── macro_metrics: commodity + treasury + index metrics ──────────────
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS copper_price numeric;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS copper_change_pct numeric;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS oil_price numeric;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS oil_change_pct numeric;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS us_10y_yield numeric;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS us_10y_change_pct numeric;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS shanghai_close numeric;
ALTER TABLE macro_metrics ADD COLUMN IF NOT EXISTS shanghai_change_pct numeric;

-- ── foreign_flow_details: per-ticker buy/sell + ownership ────────────
ALTER TABLE foreign_flow_details ADD COLUMN IF NOT EXISTS buy_value_billion numeric;
ALTER TABLE foreign_flow_details ADD COLUMN IF NOT EXISTS sell_value_billion numeric;
ALTER TABLE foreign_flow_details ADD COLUMN IF NOT EXISTS net_value_billion numeric;
ALTER TABLE foreign_flow_details ADD COLUMN IF NOT EXISTS ownership_pct numeric;
ALTER TABLE foreign_flow_details ADD COLUMN IF NOT EXISTS remaining_room bigint;

-- ── longterm_watchlist: conviction scoring + review flags ────────────
ALTER TABLE longterm_watchlist ADD COLUMN IF NOT EXISTS conviction_score integer;
ALTER TABLE longterm_watchlist ADD COLUMN IF NOT EXISTS conviction_method text DEFAULT 'manual'::text;
ALTER TABLE longterm_watchlist ADD COLUMN IF NOT EXISTS review_flags text[] DEFAULT '{}'::text[];
ALTER TABLE longterm_watchlist ADD COLUMN IF NOT EXISTS last_reviewed_at timestamp with time zone;

-- ── learnings_summary: plan-split stats ──────────────────────────────
ALTER TABLE learnings_summary ADD COLUMN IF NOT EXISTS swing_win_rate numeric;
ALTER TABLE learnings_summary ADD COLUMN IF NOT EXISTS longterm_win_rate numeric;
ALTER TABLE learnings_summary ADD COLUMN IF NOT EXISTS swing_sample_size integer;

-- ── rotation_evaluations: sector JSONB arrays ────────────────────────
ALTER TABLE rotation_evaluations ADD COLUMN IF NOT EXISTS hot_sectors jsonb DEFAULT '[]'::jsonb;
ALTER TABLE rotation_evaluations ADD COLUMN IF NOT EXISTS cold_sectors jsonb DEFAULT '[]'::jsonb;

-- ── alerts: evaluation artifacts ─────────────────────────────────────
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS triggered_values jsonb;

COMMIT;
