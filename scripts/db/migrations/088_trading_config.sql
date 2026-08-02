-- Migration 088: Trading Parameters Config Table
-- Single-row typed table for all trading constraints.
-- Eliminates hardcoded values scattered across 15+ files.

-- ── Create Table ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS trading_config (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- enforce single row

    -- Core Risk
    min_cash_reserve         BIGINT  NOT NULL DEFAULT 10000000,   -- VND reserve (never touch)
    max_risk_per_trade       BIGINT  NOT NULL DEFAULT 200000,     -- VND at risk per trade
    low_cash_threshold       BIGINT  NOT NULL DEFAULT 5000000,    -- below this → LOW_CASH mode
    max_concurrent_positions SMALLINT NOT NULL DEFAULT 3,
    transaction_cost_pct     NUMERIC(8,4) NOT NULL DEFAULT 0.003, -- 0.3% round-trip
    monthly_contribution     BIGINT  NOT NULL DEFAULT 10000000,   -- VND added per month

    -- Concentration Limits
    concentration_exit_pct          NUMERIC(5,2) NOT NULL DEFAULT 60.0,  -- any plan > 60% → EXIT
    swing_trim_weight_pct           NUMERIC(5,2) NOT NULL DEFAULT 40.0,  -- swing weight > 40% → TRIM
    swing_trim_gain_pct             NUMERIC(5,2) NOT NULL DEFAULT 15.0,  -- swing gain > 15% → TRIM
    longterm_trim_weight_high_pct   NUMERIC(5,2) NOT NULL DEFAULT 55.0,  -- longterm > 55% → TRIM high
    longterm_trim_weight_med_pct    NUMERIC(5,2) NOT NULL DEFAULT 45.0,  -- longterm > 45% → TRIM med
    longterm_review_weight_pct      NUMERIC(5,2) NOT NULL DEFAULT 30.0,  -- informational review threshold
    sector_concentration_high_pct   NUMERIC(5,2) NOT NULL DEFAULT 60.0,  -- >60% same cluster → HIGH
    sector_concentration_med_pct    NUMERIC(5,2) NOT NULL DEFAULT 40.0,  -- >40% same cluster → MEDIUM

    -- Trailing Stops (SWING)
    breakeven_gain_pct       NUMERIC(5,2) NOT NULL DEFAULT 10.0,  -- up to 10% gain → use breakeven
    half_trail_gain_pct      NUMERIC(5,2) NOT NULL DEFAULT 15.0,  -- 10-15% gain → 50% trail
    tight_trail_gain_pct     NUMERIC(5,2) NOT NULL DEFAULT 15.0,  -- >15% gain → tight trail
    tight_current_floor_pct  NUMERIC(5,2) NOT NULL DEFAULT 95.0,  -- floor at current * 0.95
    tight_gain_lock_pct      NUMERIC(5,2) NOT NULL DEFAULT 75.0,  -- entry + gain * 0.75
    longterm_catastrophic_pct NUMERIC(5,2) NOT NULL DEFAULT 20.0, -- longterm floor: entry * (1 - 0.20)

    -- Win Rate Position Scale
    full_winrate_threshold    NUMERIC(5,2) NOT NULL DEFAULT 50.0,  -- >= 50% → 1.0x
    reduced_winrate_threshold NUMERIC(5,2) NOT NULL DEFAULT 35.0,  -- >= 35% → 0.75x
    half_winrate_threshold    NUMERIC(5,2) NOT NULL DEFAULT 20.0,  -- >= 20% → 0.5x
    minimal_scale_factor      NUMERIC(4,3) NOT NULL DEFAULT 0.25,  -- < 20% → 0.25x

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Seed defaults (single-row upsert) ────────────────────────────────────────

INSERT INTO trading_config (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;

-- ── Update SQL functions to reference trading_config ─────────────────────────

-- Use RETURN syntax (PostgreSQL 14+) to avoid semicolons inside dollar-quoted bodies,
-- which confuses the migration runner's semicolon-based statement splitter.

CREATE OR REPLACE FUNCTION get_deployable_cash(cash_balance bigint)
RETURNS bigint
LANGUAGE SQL
STABLE
RETURN GREATEST(0, cash_balance - (SELECT min_cash_reserve FROM trading_config LIMIT 1));

CREATE OR REPLACE FUNCTION get_trading_mode(deployable_cash bigint)
RETURNS text
LANGUAGE SQL
STABLE
RETURN CASE
    WHEN deployable_cash > (SELECT low_cash_threshold FROM trading_config LIMIT 1) THEN 'NORMAL'
    WHEN deployable_cash > 0 THEN 'LOW_CASH'
    ELSE 'REALLOCATION'
END;

-- NOTE: v_swing_metrics view update is intentionally omitted here.
-- If that view references hardcoded 10000000, update it in a separate migration
-- using CREATE OR REPLACE VIEW once the view definition is confirmed.
