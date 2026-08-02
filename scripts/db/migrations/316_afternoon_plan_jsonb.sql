-- Migration 316: afternoon_plan TEXT -> JSONB list[AfternoonAction].
--
-- Structural fix deferred at commit e8f5b814 ship. Free-text surface let
-- midday re-open the token-overrun failure mode and produced slice-bug
-- garbage at retro interpolation (`afternoon_plan[:100]` on a list).
--
-- Shape per row is a JSON array of action objects:
--   [
--     {"ticker": "FPT"|null,
--      "action": "BUY"|"HOLD"|"TRIM"|"EXIT"|"NOTE"|"CANCEL"|"WATCH",
--      "confidence": "HIGH"|"MEDIUM"|"LOW",
--      "reason": "..."}
--   ]
--
-- Legacy rows seed as a single NOTE with the original text. `null` ticker
-- is semantically correct — legacy rows have no structured ticker, and
-- retro aggregation in scripts/retro_helpers/learnings.py already skips
-- null-ticker entries in ticker-keyed rollups.
--
-- Forward-only. Apply to local Docker + staging before prod per 305-315
-- convention.

BEGIN;

-- 1. midday_checks.afternoon_plan
ALTER TABLE midday_checks
    ALTER COLUMN afternoon_plan
    TYPE JSONB
    USING CASE
        WHEN afternoon_plan IS NULL OR afternoon_plan = '' THEN '[]'::jsonb
        ELSE jsonb_build_array(
            jsonb_build_object(
                'ticker', NULL,
                'action', 'NOTE',
                'confidence', 'LOW',
                'reason', afternoon_plan
            )
        )
    END;

COMMENT ON COLUMN midday_checks.afternoon_plan IS
    'Structured afternoon plan (list[AfternoonAction]). Pre-2026-04-20 TEXT rows seeded '
    'as single NOTE entries with ticker=null and confidence=LOW. See migration 316.';

-- 2. midday_data.afternoon_plan
ALTER TABLE midday_data
    ALTER COLUMN afternoon_plan
    TYPE JSONB
    USING CASE
        WHEN afternoon_plan IS NULL OR afternoon_plan = '' THEN '[]'::jsonb
        ELSE jsonb_build_array(
            jsonb_build_object(
                'ticker', NULL,
                'action', 'NOTE',
                'confidence', 'LOW',
                'reason', afternoon_plan
            )
        )
    END;

COMMENT ON COLUMN midday_data.afternoon_plan IS
    'Structured afternoon plan (list[AfternoonAction]). Mirrors midday_checks.afternoon_plan. '
    'See migration 316.';

INSERT INTO schema_migrations (version) VALUES ('316_afternoon_plan_jsonb')
ON CONFLICT (version) DO NOTHING;

COMMIT;
