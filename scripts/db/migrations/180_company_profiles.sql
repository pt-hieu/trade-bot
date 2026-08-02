-- Migration 180: Company profiles knowledge base for macro → ticker mapping
-- DDL — requires owner connection URL

CREATE TABLE IF NOT EXISTS company_profiles (
    ticker              TEXT PRIMARY KEY REFERENCES stocks(ticker),
    sector_id           INTEGER REFERENCES sectors(id),
    business_summary    TEXT,
    revenue_segments    JSONB DEFAULT '[]',
    supply_chain        JSONB DEFAULT '[]',
    export_split        JSONB DEFAULT '{}',
    macro_sensitivities JSONB DEFAULT '[]',
    regulatory_exposure JSONB DEFAULT '[]',
    competitive_position JSONB DEFAULT '{}',
    source              TEXT NOT NULL DEFAULT 'manual',
    version             INTEGER NOT NULL DEFAULT 1,
    research_date       DATE NOT NULL DEFAULT CURRENT_DATE,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- JSONB field schemas:
-- revenue_segments:    [{name, pct_revenue, description}]
-- supply_chain:        [{input, source_countries, pct_cost}]
-- export_split:        {domestic_pct, exports: [{market, pct_revenue}]}
-- macro_sensitivities: [{factor, direction(POSITIVE|NEGATIVE|MIXED), magnitude(HIGH|MEDIUM|LOW), explanation}]
-- regulatory_exposure: [{policy, impact(POSITIVE|NEGATIVE|MIXED), description}]
-- competitive_position:{market_share, moat(WIDE|NARROW|NONE), pricing_power(HIGH|MEDIUM|LOW), description}

-- GIN index for macro factor containment queries: @> '[{"factor": "oil_price"}]'
CREATE INDEX IF NOT EXISTS idx_cp_macro ON company_profiles USING GIN (macro_sensitivities);

-- Sector lookup
CREATE INDEX IF NOT EXISTS idx_cp_sector ON company_profiles (sector_id);
