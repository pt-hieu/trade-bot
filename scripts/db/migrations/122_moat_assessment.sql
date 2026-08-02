-- Migration 122: Add structured moat assessment to company_research
ALTER TABLE company_research ADD COLUMN IF NOT EXISTS moat_assessment JSONB;
-- Schema: {
--   network_effects: "STRONG|MODERATE|WEAK|NONE",
--   switching_costs: "STRONG|MODERATE|WEAK|NONE",
--   scale_economies: "STRONG|MODERATE|WEAK|NONE",
--   intangible_assets: "STRONG|MODERATE|WEAK|NONE",
--   fol_premium: bool,        -- benefits from FOL premium
--   state_ownership: bool,    -- state ownership provides advantages
--   regulatory_license: bool, -- holds hard-to-get licenses
--   overall_moat: "WIDE|NARROW|NONE",
--   moat_score: int,          -- 0-100 deterministic from ratings
--   assessed_at: "date"
-- }
CREATE INDEX IF NOT EXISTS idx_company_research_moat
ON company_research USING GIN (moat_assessment)
WHERE moat_assessment IS NOT NULL;
