-- Migration 071: Refiner override audit trail
-- Tracks structural changes made by the refiner agent during the reflection loop.
-- Enables tracing "refiner removed X because of Y" back to source agents over time.

CREATE TABLE IF NOT EXISTS refiner_overrides (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    record_date DATE NOT NULL,
    iteration INTEGER NOT NULL,           -- 1, 2, or 3 (reflection loop pass)
    ticker VARCHAR(10),                   -- NULL for section-level changes
    original_action VARCHAR(20),          -- BUY, HOLD, EXIT, etc. (what brief said before)
    override_action VARCHAR(20) NOT NULL, -- REMOVED, DOWNGRADED, REWRITTEN, ADDED, DELETED
    category VARCHAR(50) NOT NULL,        -- rr_failure, mode_violation, regime_violation,
                                          -- holdings_mismatch, section_fix, format_fix, logic_fix
    critic_issue TEXT NOT NULL,           -- the critic issue that triggered this change
    detail TEXT,                          -- what specifically changed and why
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refiner_overrides_date
    ON refiner_overrides(record_date);

CREATE INDEX IF NOT EXISTS idx_refiner_overrides_ticker
    ON refiner_overrides(ticker, record_date);
