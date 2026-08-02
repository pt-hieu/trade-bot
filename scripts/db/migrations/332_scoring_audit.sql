-- 332_scoring_audit.sql
-- SWI-171 Phase A: deterministic 0-100 BUY-candidate score audit tables.
--
-- This migration adds the audit substrate the scorer writes during Phase A
-- (audit-only mode — zero behavioral delta). One row per pre-gate
-- candidate per pipeline run, capturing the score, breakdown, weight
-- snapshot, scoring_version, and which rejection layer (if any) dropped
-- the candidate.
--
-- Cross-references:
--   * SWI-60  (belief_flattening) — upstream signal collapse this audit
--               cannot observe (sector aggregator returns 0 BULLISH);
--               the `signals_audit` table tracks that frontier.
--   * SWI-132 (sector_technical starvation) — trade_setup unresolvable
--               drops surface here as `gated_by='setup_invalid'`.
--   * SWI-93  (canonical zero-BUY bug).
--   * SWI-167 / SWI-166 — pre-cutover composer state.
--
-- Idempotent: every CREATE/ALTER uses IF NOT EXISTS / IF EXISTS so the
-- migration can be re-run after a partial apply without dirtying state.
-- No DML side effects in Phase A — Phase B will drop legacy R:R floor
-- columns in a separate migration.
--
-- Apply (per project_lightsail_psql_bastion.md, 2026-04-21):
--   scp this file to the Lightsail bastion ($LIGHTSAIL_SSH_TARGET)
--   ssh-run: psql "<owner_url>" -v ON_ERROR_STOP=1 -f 332_scoring_audit.sql
--   record: psql "<owner_url>" -c "INSERT INTO schema_migrations (version)
--           VALUES ('332_scoring_audit') ON CONFLICT DO NOTHING;"

BEGIN;

-- ─────────────────────────────────────────────────────────────────────
-- Enums (idempotent — gate_phase + gated_by_kind + miss_kind).
-- ─────────────────────────────────────────────────────────────────────

DO $$ BEGIN
  CREATE TYPE scoring_phase AS ENUM ('morning', 'midday', 'retro');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE gated_by_kind AS ENUM (
    'setup_invalid',
    'trend_momentum',
    'atr_trail_rr_gate',
    'rr_floor',
    'sizing_floor',
    'validator_max_picks',
    'passed'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE candidate_source AS ENUM ('sector', 'belief_fallback');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE near_miss_kind AS ENUM (
    'score_below_threshold',
    'no_resolvable_setup'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ─────────────────────────────────────────────────────────────────────
-- pre_gate_candidates: one row per candidate seen at picks.py:122.
-- Score is computed BEFORE any rejection layer (per /challenge round-1
-- finding). `gated_by` = 'passed' means the candidate cleared layers 1-5.
-- ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pre_gate_candidates (
    id                          BIGSERIAL PRIMARY KEY,

    -- Composite identity (date, ticker, phase) — natural key.
    scan_date                   DATE          NOT NULL,
    ticker                      TEXT          NOT NULL,
    phase                       scoring_phase NOT NULL,

    -- Score + breakdown (deterministic, computed by shared/rules/scoring.py)
    score                       NUMERIC(7,4)  NOT NULL,
    breakdown                   JSONB         NOT NULL,
    base_score                  NUMERIC(7,4)  NOT NULL,
    regime_penalty              NUMERIC(7,4)  NOT NULL DEFAULT 0,
    shock_penalty               NUMERIC(7,4)  NOT NULL DEFAULT 0,
    threshold_at_run            INT           NOT NULL,
    weights_jsonb               JSONB         NOT NULL,
    scoring_version             TEXT          NOT NULL,

    -- Rejection-layer attribution
    gated_by                    gated_by_kind NOT NULL,
    gate_reason                 TEXT,
    would_pass_score_gate       BOOLEAN       NOT NULL,

    -- 13 raw feature values (all NULL-able; setup_invalid drops have
    -- many NULLs by construction).
    feature_risk_reward         NUMERIC(7,4),
    feature_sim_p_target        NUMERIC(5,4),
    feature_sim_p_stop          NUMERIC(5,4),
    feature_sim_ev              NUMERIC(7,4),
    feature_strategy_confidence NUMERIC(5,4),
    feature_belief_conviction   NUMERIC(5,4),
    feature_catalyst_strength   NUMERIC(5,4),
    feature_bullish_belief_count INT,
    feature_total_sector_count  INT,
    feature_rs_20d              NUMERIC(7,4),
    feature_volume_vs_avg       NUMERIC(7,4),
    feature_trend_alignment     TEXT,
    feature_foreign_net_strength NUMERIC(20,2),
    feature_order_imbalance     NUMERIC(5,4),

    -- Relief context (suppressor predicate inputs + decision)
    relief_eligible             BOOLEAN       NOT NULL DEFAULT FALSE,
    relief_block_reason         TEXT,

    -- Context columns
    sector                      TEXT,
    source                      candidate_source NOT NULL DEFAULT 'sector',
    regime                      TEXT          NOT NULL,
    urgency_tier                TEXT,

    created_at                  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT pre_gate_candidates_unique UNIQUE (scan_date, ticker, phase)
);

CREATE INDEX IF NOT EXISTS pre_gate_candidates_date_idx
  ON pre_gate_candidates (scan_date DESC);

CREATE INDEX IF NOT EXISTS pre_gate_candidates_gated_by_idx
  ON pre_gate_candidates (scan_date, gated_by);

CREATE INDEX IF NOT EXISTS pre_gate_candidates_score_desc_idx
  ON pre_gate_candidates (scan_date, score DESC);

COMMENT ON TABLE pre_gate_candidates IS
  'SWI-171 Phase A: deterministic score audit row for every BUY candidate '
  'reaching agents/picks.py:122 — rejected and survived. Phase B promotion '
  'gate fits weights against this distribution. Cross-refs SWI-60 (upstream '
  'belief flattening invisible here) and SWI-132 (setup_invalid attribution).';

COMMENT ON COLUMN pre_gate_candidates.weights_jsonb IS
  'Snapshot of the active weights vector at the time the row was written. '
  'Phase B replay determinism depends on this — DO NOT migrate weights to '
  'trading_config without first preserving snapshot semantics.';

COMMENT ON COLUMN pre_gate_candidates.scoring_version IS
  'SemVer of scripts/agents/configs/scoring.yaml. Bumped on every weight '
  'or normalize() math change. Pre-commit hook enforces co-bump on diff.';

COMMENT ON COLUMN pre_gate_candidates.gated_by IS
  'Which layer dropped the candidate, or `passed` if it cleared all 5. '
  'Layer 1=setup_invalid (picks.py:126,133). Layer 2=trend_momentum '
  '(picks.py:166). Layer 3=atr_trail_rr_gate (picks_exit_dispatch.py:66). '
  'Layer 4=rr_floor or sizing_floor (entry_gates.check_candidate_gate). '
  'Layer 5=validator_max_picks (recommendation_validator.py Pass 3).';

-- ─────────────────────────────────────────────────────────────────────
-- near_miss_candidates: top-N near-miss surface for the daily brief
-- (Phase B rendering) and retro analytics. Phase A populates excluding
-- `setup_invalid` rows so the LIMIT 3 surface is meaningful.
-- ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS near_miss_candidates (
    id              BIGSERIAL PRIMARY KEY,

    scan_date       DATE            NOT NULL,
    rank            INT             NOT NULL,
    ticker          TEXT            NOT NULL,
    score           NUMERIC(7,4)    NOT NULL,
    breakdown       JSONB           NOT NULL,
    miss_kind       near_miss_kind  NOT NULL DEFAULT 'score_below_threshold',
    sector          TEXT,

    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT near_miss_unique UNIQUE (scan_date, ticker, miss_kind)
);

CREATE INDEX IF NOT EXISTS near_miss_candidates_date_rank_idx
  ON near_miss_candidates (scan_date DESC, rank ASC);

COMMENT ON TABLE near_miss_candidates IS
  'SWI-171: top-3 score-misses persisted daily for the synthesis '
  'near-miss block (Phase B rendering) and retro analytics. Phase A '
  'top-3 query selects from pre_gate_candidates where '
  'gated_by != setup_invalid ordered by score desc limit 3 — exclusion '
  'prevents score=0 leakage.';

-- ─────────────────────────────────────────────────────────────────────
-- signals_audit: BULLISH belief count per sector BEFORE picks.py loop.
-- Closes the round-3 architectural #4 gap — Phase A audit cannot see
-- upstream sector aggregator collapse (SWI-60) without this surface.
-- ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS signals_audit (
    id                    BIGSERIAL PRIMARY KEY,

    scan_date             DATE          NOT NULL,
    phase                 scoring_phase NOT NULL,
    sector                TEXT          NOT NULL,

    bullish_belief_count  INT           NOT NULL DEFAULT 0,
    total_signal_count    INT           NOT NULL DEFAULT 0,
    buy_signal_count      INT           NOT NULL DEFAULT 0,

    created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT signals_audit_unique UNIQUE (scan_date, phase, sector)
);

CREATE INDEX IF NOT EXISTS signals_audit_date_idx
  ON signals_audit (scan_date DESC);

COMMENT ON TABLE signals_audit IS
  'SWI-171 round-3 architectural #4: per-sector BULLISH belief denominator '
  'BEFORE picks loop runs. Distinguishes "we considered N beliefs upstream" '
  'from "the picks loop filtered out N candidates". Cross-refs SWI-60.';

COMMIT;
