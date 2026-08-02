-- Migration 018: Add pinned column to swing_watchlist
-- Pinned stocks cannot be removed by automated weekly updates.

-- Add is_pinned column
ALTER TABLE swing_watchlist
ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE;

-- Add pin_reason for audit trail
ALTER TABLE swing_watchlist
ADD COLUMN IF NOT EXISTS pin_reason TEXT;

-- Ensure FOX exists in stocks table (FK requirement)
INSERT INTO stocks (ticker, company_name, sector_id, stock_type)
VALUES ('FOX', 'FPT Telecom', (SELECT id FROM sectors WHERE LOWER(name) = 'technology'), 'Private')
ON CONFLICT (ticker) DO NOTHING;

-- Insert FOX into swing_watchlist as pinned
INSERT INTO swing_watchlist (ticker, sector_id, stock_type, is_pinned, pin_reason, is_active)
VALUES (
    'FOX',
    (SELECT id FROM sectors WHERE LOWER(name) = 'technology'),
    'Private',
    TRUE,
    'Piracy crackdown catalyst (Xoilac/Vebo/RoPhim shutdown Feb 2026) - FPT Play user migration',
    TRUE
)
ON CONFLICT (ticker) DO UPDATE SET
    is_active = TRUE,
    is_pinned = TRUE,
    pin_reason = EXCLUDED.pin_reason,
    updated_at = NOW();
