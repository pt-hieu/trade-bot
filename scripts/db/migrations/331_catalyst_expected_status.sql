-- 331_catalyst_expected_status.sql
-- SWI-18 (2026-04-27): post-LLM expected_date parser + structured
-- `expected_status` enum.
--
-- Problem: 12/40 active catalysts emit free text ("ongoing", "Effective
-- immediately", narrative without temporal tokens) and land in `catalysts`
-- with `expected_date IS NULL`. The 21d imminent gate, 14d past-date
-- expiry path, and 45/90d NULL fallback all miss these rows — they
-- escape lifecycle scoring forever.
--
-- Fix: a new `expected_status` enum column distinguishes intentionally-
-- dateless catalysts (`ongoing`) from genuine parser-failures
-- (`unparseable`) and gives `refresh_catalyst_lifecycle` a tighter 14d
-- staleness for the latter. Phrase + regex backfills also write parsed
-- `expected_date` values so the active fleet stops slipping through.
--
-- Bias rule (matches scripts/shared/rules/catalyst_expected_parser.py):
-- pure narrative without a temporal token → `ongoing`. Only when a
-- temporal token is present AND parsing fails do we mark `unparseable`.
--
-- Backfills are CONDITIONAL — every UPDATE filters on
-- `status IN ('active','monitoring','imminent')` so resolved/expired
-- history is never mutated.

BEGIN;

ALTER TABLE catalysts
  ADD COLUMN IF NOT EXISTS expected_status TEXT
  CHECK (
    expected_status IN ('dated','quarter','month','relative','ongoing','unparseable')
  );

-- Step 1 — explicit ongoing phrases. TRIM + REGEXP_REPLACE strips trailing
-- punctuation and unicode quirks before the membership check.
UPDATE catalysts
SET expected_status = 'ongoing',
    updated_at = NOW()
WHERE expected_status IS NULL
  AND expected_date IS NULL
  AND status IN ('active','monitoring','imminent')
  AND TRIM(LOWER(REGEXP_REPLACE(expected, '[^a-z0-9 ]', '', 'g'))) IN (
    'ongoing',
    'effective immediately',
    'continuous',
    'tbd',
    'indefinite',
    'until further notice',
    'in due course',
    'n a',
    'none',
    ''
  );

-- Step 2 — ISO date parse `YYYY-MM-DD`. Only writes a date when none was
-- previously persisted; status flips to `dated`.
UPDATE catalysts
SET expected_date = (SUBSTRING(expected FROM '\d{4}-\d{1,2}-\d{1,2}'))::date,
    expected_status = 'dated',
    updated_at = NOW()
WHERE expected_status IS NULL
  AND expected_date IS NULL
  AND status IN ('active','monitoring','imminent')
  AND expected ~* '\b\d{4}-\d{1,2}-\d{1,2}\b';

-- Step 3 — quarter labels `Qn YYYY`. Map to last day of the quarter.
-- The CASE picks end-of-month for Q1=Mar, Q2=Jun, Q3=Sep, Q4=Dec.
UPDATE catalysts
SET expected_date = (
      CASE SUBSTRING(LOWER(expected) FROM '\bq([1-4])\b')
        WHEN '1' THEN MAKE_DATE(SUBSTRING(expected FROM '\b(20\d{2})\b')::int, 3, 31)
        WHEN '2' THEN MAKE_DATE(SUBSTRING(expected FROM '\b(20\d{2})\b')::int, 6, 30)
        WHEN '3' THEN MAKE_DATE(SUBSTRING(expected FROM '\b(20\d{2})\b')::int, 9, 30)
        WHEN '4' THEN MAKE_DATE(SUBSTRING(expected FROM '\b(20\d{2})\b')::int, 12, 31)
      END
    ),
    expected_status = 'quarter',
    updated_at = NOW()
WHERE expected_status IS NULL
  AND expected_date IS NULL
  AND status IN ('active','monitoring','imminent')
  AND expected ~* '\bq[1-4]\b'
  AND expected ~* '\b20\d{2}\b';

-- Step 4 — month labels `<MonthName> YYYY`. Map to last day of the month.
UPDATE catalysts
SET expected_date = (
      MAKE_DATE(
        SUBSTRING(expected FROM '\b(20\d{2})\b')::int,
        CASE SUBSTRING(LOWER(expected) FROM '\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)')
          WHEN 'jan' THEN 1 WHEN 'feb' THEN 2 WHEN 'mar' THEN 3 WHEN 'apr' THEN 4
          WHEN 'may' THEN 5 WHEN 'jun' THEN 6 WHEN 'jul' THEN 7 WHEN 'aug' THEN 8
          WHEN 'sep' THEN 9 WHEN 'oct' THEN 10 WHEN 'nov' THEN 11 WHEN 'dec' THEN 12
        END,
        1
      )
      + INTERVAL '1 month' - INTERVAL '1 day'
    )::date,
    expected_status = 'month',
    updated_at = NOW()
WHERE expected_status IS NULL
  AND expected_date IS NULL
  AND status IN ('active','monitoring','imminent')
  AND expected ~* '\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+20\d{2}\b';

-- Step 5 — anything still NULL with no temporal token → ongoing (bias rule).
UPDATE catalysts
SET expected_status = 'ongoing',
    updated_at = NOW()
WHERE expected_status IS NULL
  AND expected_date IS NULL
  AND status IN ('active','monitoring','imminent')
  AND expected !~* '\b(20\d{2}|q[1-4]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|days?|weeks?|months?)\b';

-- Step 6 — anything still NULL after step 5 has a temporal token but did
-- not match any pattern → unparseable.
UPDATE catalysts
SET expected_status = 'unparseable',
    updated_at = NOW()
WHERE expected_status IS NULL
  AND expected_date IS NULL
  AND status IN ('active','monitoring','imminent');

-- Audit: distribution by status.
SELECT expected_status, COUNT(*)
FROM catalysts
WHERE status IN ('active','monitoring','imminent')
GROUP BY expected_status
ORDER BY expected_status;

COMMIT;
