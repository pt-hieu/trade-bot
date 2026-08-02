-- Add missed_opportunities column to macro_patterns
-- Tracks days where defensive regime (CAUTIOUS/ELEVATED/CRISIS) was called
-- but market rallied >1.5%, indicating opportunity cost of over-caution.
ALTER TABLE macro_patterns ADD COLUMN IF NOT EXISTS missed_opportunities INTEGER DEFAULT 0;
