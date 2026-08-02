-- =====================================================
-- MIGRATION 009: Add plan_type to distinguish Swing vs Long-term
-- =====================================================

-- Create enum for plan types (will error if exists, that's OK)
CREATE TYPE plan_type AS ENUM ('SWING', 'LONGTERM');

-- Add plan_type to trades_calculated (default SWING)
ALTER TABLE trades_calculated
ADD COLUMN IF NOT EXISTS plan_type plan_type DEFAULT 'SWING';

-- Add plan_type to portfolio_holdings (default SWING)
ALTER TABLE portfolio_holdings
ADD COLUMN IF NOT EXISTS plan_type plan_type DEFAULT 'SWING';

-- Create index for filtering by plan
CREATE INDEX IF NOT EXISTS idx_trades_calc_plan ON trades_calculated(plan_type);
CREATE INDEX IF NOT EXISTS idx_portfolio_plan ON portfolio_holdings(plan_type);

-- Mark TCFIN as LONGTERM
UPDATE portfolio_holdings
SET plan_type = 'LONGTERM'
WHERE ticker = 'TCFIN';

UPDATE trades_calculated
SET plan_type = 'LONGTERM'
WHERE ticker = 'TCFIN';
