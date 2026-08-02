-- Migration 107: Sector Allocation Config Table
-- Replaces hardcoded UNION ALL in v_longterm_allocation with configurable rows.
-- Eliminates 50/35/15 targets hardcoded in migration 017 and agent prompts.

-- ── Create Table ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sector_allocations (
    id          SERIAL PRIMARY KEY,
    sector_name VARCHAR(50) NOT NULL UNIQUE,  -- matches sectors.name (snake_case)
    target_pct  NUMERIC(5,2) NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Seed current allocations ──────────────────────────────────────────────────

INSERT INTO sector_allocations (sector_name, target_pct) VALUES
    ('technology', 50.0),
    ('real_estate', 35.0),
    ('banking', 15.0)
ON CONFLICT (sector_name) DO NOTHING;

-- ── Recreate v_longterm_allocation to use sector_allocations ─────────────────
-- Previously defined in migration 017 with hardcoded targets CTE.
-- Now reads target_pct from the configurable sector_allocations table.

DROP VIEW IF EXISTS v_longterm_allocation CASCADE;

CREATE VIEW v_longterm_allocation AS
WITH holdings_by_sector AS (
    SELECT
        COALESCE(s.name, 'other') AS sector,
        COALESCE(s.display_name, 'Other') AS sector_display,
        SUM(p.market_value_vnd) AS market_value
    FROM portfolio_holdings p
    LEFT JOIN stocks st ON p.ticker = st.ticker
    LEFT JOIN sectors s ON st.sector_id = s.id
    WHERE p.holding_type != 'Cash' AND p.shares > 0 AND p.plan_type = 'LONGTERM'
    GROUP BY s.name, s.display_name
),
total AS (
    SELECT SUM(market_value) AS total_value FROM holdings_by_sector
)
SELECT
    h.sector_display AS sector,
    h.market_value AS market_value_vnd,
    ROUND(h.market_value::NUMERIC / NULLIF(t.total_value, 0) * 100, 1) AS actual_pct,
    COALESCE(sa.target_pct, 0) AS target_pct,
    ROUND(h.market_value::NUMERIC / NULLIF(t.total_value, 0) * 100 - COALESCE(sa.target_pct, 0), 1) AS drift_pct,
    CASE
        WHEN ROUND(h.market_value::NUMERIC / NULLIF(t.total_value, 0) * 100, 1) > COALESCE(sa.target_pct, 0) + 5 THEN 'OVERWEIGHT'
        WHEN ROUND(h.market_value::NUMERIC / NULLIF(t.total_value, 0) * 100, 1) < COALESCE(sa.target_pct, 0) - 5 THEN 'UNDERWEIGHT'
        ELSE 'ON_TARGET'
    END AS status
FROM holdings_by_sector h
CROSS JOIN total t
LEFT JOIN sector_allocations sa ON h.sector = sa.sector_name
ORDER BY h.market_value DESC;
