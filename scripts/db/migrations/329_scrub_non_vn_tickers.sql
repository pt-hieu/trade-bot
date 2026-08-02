-- Migration 329: Scrub non-VN tickers from affected_tickers columns.
--
-- Context: AUDIT-2026-04-24-001 / ISSUE-2026-04-24-005.
-- LLM ticker extraction was drifting toward non-VN codes (UAE, XIV, IBM,
-- KMI, PSX, WHR, …) because the prompt never enumerated the authoritative
-- VN universe. Post-filter + anchor injection now land at the producer,
-- but the historic rows in articles / narratives still hold the junk.
--
-- This migration removes any element from the `affected_tickers` array
-- that is not VN-listed (UNION of `company_profiles` + active `stocks`)
-- and is not the reserved macro/geopolitical placeholder `VN-INDEX`.

BEGIN;

-- One-shot CTE of the accepted token set so both UPDATEs agree.
CREATE TEMP TABLE _vn_universe ON COMMIT DROP AS
SELECT ticker
FROM company_profiles
UNION
SELECT ticker
FROM stocks
WHERE is_active = TRUE
UNION
SELECT 'VN-INDEX';

-- Articles (news-pipeline per-article tags).
UPDATE articles
SET affected_tickers = COALESCE(
    ARRAY(
        SELECT token
        FROM unnest(affected_tickers) AS token
        WHERE token IN (SELECT ticker FROM _vn_universe)
    ),
    ARRAY[]::text[]
)
WHERE affected_tickers IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM unnest(affected_tickers) AS token
      WHERE token NOT IN (SELECT ticker FROM _vn_universe)
  );

-- Narratives (inherits junk via narrative_labeler's affected_tickers field).
UPDATE narratives
SET affected_tickers = COALESCE(
    ARRAY(
        SELECT token
        FROM unnest(affected_tickers) AS token
        WHERE token IN (SELECT ticker FROM _vn_universe)
    ),
    ARRAY[]::text[]
)
WHERE affected_tickers IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM unnest(affected_tickers) AS token
      WHERE token NOT IN (SELECT ticker FROM _vn_universe)
  );

COMMIT;
