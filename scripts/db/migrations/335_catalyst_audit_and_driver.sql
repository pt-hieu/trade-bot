-- 335_catalyst_audit_and_driver.sql
--
-- Two small additions for catalyst-tagging observability:
--
--   1. catalyst_rejections.rule_corrected_type — when the rule layer coerces
--      an LLM-supplied catalyst_type, log the new type alongside the old.
--      Lets retro answer "how often is the LLM wrong about X?" without
--      scraping logs.
--
--   2. catalysts.driver — structured "primary force" the catalysts agent
--      commits to before picking catalyst_type. Allowlist mirrors the
--      `CatalystDriver` Literal in scripts/shared/post_llm_types.py.

BEGIN;

ALTER TABLE catalyst_rejections
    ADD COLUMN IF NOT EXISTS rule_corrected_type VARCHAR(50);

ALTER TABLE catalysts
    ADD COLUMN IF NOT EXISTS driver VARCHAR(50);

-- DB enum parity (CLAUDE.md): allowlist must match the Python `CatalystDriver`
-- Literal. Extend both together when adding values.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'catalysts_driver_allowed'
    ) THEN
        ALTER TABLE catalysts
            ADD CONSTRAINT catalysts_driver_allowed
            CHECK (driver IS NULL OR driver IN (
                'state_actor',
                'commodity_supply',
                'company_action',
                'regulator',
                'earnings_cycle'
            ));
    END IF;
END $$;

COMMENT ON COLUMN catalyst_rejections.rule_corrected_type IS
    'When classify_catalyst_type coerces the LLM-supplied candidate_type, '
    'the new type is logged here. NULL on the rejected branch.';

COMMENT ON COLUMN catalysts.driver IS
    'Structured primary force emitted by the catalysts agent (state_actor, '
    'commodity_supply, company_action, regulator, earnings_cycle). Lets us '
    'spot driver/type mismatches in queries.';

COMMIT;
