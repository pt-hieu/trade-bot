-- Add securities sector for brokerage stocks (SSI, VCI, HCM, VIX, VND)
-- These are direct FTSE upgrade beneficiaries — higher liquidity = more brokerage revenue

-- 1. Add securities sector
INSERT INTO sectors (name, display_name) VALUES ('securities', 'Securities')
ON CONFLICT (name) DO NOTHING;

-- 2. Ensure stocks table has VCI and HCM
INSERT INTO stocks (ticker, sector_id, stock_type)
SELECT 'VCI', id, 'Securities' FROM sectors WHERE name = 'securities'
ON CONFLICT DO NOTHING;

INSERT INTO stocks (ticker, sector_id, stock_type)
SELECT 'HCM', id, 'Securities' FROM sectors WHERE name = 'securities'
ON CONFLICT DO NOTHING;

-- 3. Add VCI and HCM to swing_watchlist (pinned)
INSERT INTO swing_watchlist (ticker, sector_id, stock_type, is_active, is_pinned, pin_reason)
SELECT 'VCI', id, 'Securities', TRUE, TRUE, 'FTSE upgrade — securities sector direct beneficiary'
FROM sectors WHERE name = 'securities'
ON CONFLICT (ticker) DO UPDATE SET
  sector_id = EXCLUDED.sector_id, stock_type = EXCLUDED.stock_type,
  is_active = TRUE, is_pinned = TRUE, pin_reason = EXCLUDED.pin_reason;

INSERT INTO swing_watchlist (ticker, sector_id, stock_type, is_active, is_pinned, pin_reason)
SELECT 'HCM', id, 'Securities', TRUE, TRUE, 'FTSE upgrade — securities sector direct beneficiary'
FROM sectors WHERE name = 'securities'
ON CONFLICT (ticker) DO UPDATE SET
  sector_id = EXCLUDED.sector_id, stock_type = EXCLUDED.stock_type,
  is_active = TRUE, is_pinned = TRUE, pin_reason = EXCLUDED.pin_reason;

-- 4. Move SSI from Technology to Securities + pin
UPDATE swing_watchlist
SET sector_id = (SELECT id FROM sectors WHERE name = 'securities'),
    stock_type = 'Securities',
    is_pinned = TRUE,
    pin_reason = 'FTSE upgrade — securities sector direct beneficiary',
    updated_at = NOW()
WHERE ticker = 'SSI';

-- 5. Move VIX from Technology to Securities + pin
UPDATE swing_watchlist
SET sector_id = (SELECT id FROM sectors WHERE name = 'securities'),
    stock_type = 'Securities',
    is_pinned = TRUE,
    pin_reason = 'FTSE upgrade — securities sector direct beneficiary',
    updated_at = NOW()
WHERE ticker = 'VIX';

-- 6. Update stocks table sector for SSI and VIX
UPDATE stocks
SET sector_id = (SELECT id FROM sectors WHERE name = 'securities'),
    stock_type = 'Securities'
WHERE ticker IN ('SSI', 'VIX');
