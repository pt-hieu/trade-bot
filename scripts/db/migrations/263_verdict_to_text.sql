-- Widen verdict from VARCHAR(20) to TEXT for actionable sentence directives.
-- Previously stored sizing hints ("full_size"/"partial_size") for TOP_PICKS only.
-- Now stores 1-2 sentence verdicts for all recommendation sections.
-- PostgreSQL VARCHAR->TEXT is metadata-only, no table rewrite.
ALTER TABLE daily_recommendations ALTER COLUMN verdict TYPE TEXT;
