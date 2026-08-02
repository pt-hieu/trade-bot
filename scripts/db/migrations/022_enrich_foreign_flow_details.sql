-- Migration 022: Enrich foreign_flow_details with per-ticker data
-- Adds buy/sell breakdown, ownership %, and remaining foreign room per ticker

-- Drop old CHECK constraint that only allows 'bought'/'sold'
ALTER TABLE foreign_flow_details
  DROP CONSTRAINT IF EXISTS foreign_flow_details_flow_type_check;

-- Re-add with 'holding' included
ALTER TABLE foreign_flow_details
  ADD CONSTRAINT foreign_flow_details_flow_type_check
  CHECK (flow_type IN ('bought', 'sold', 'holding'));

-- New columns for per-ticker enrichment
ALTER TABLE foreign_flow_details
  ADD COLUMN IF NOT EXISTS buy_value_billion DECIMAL(12,2),
  ADD COLUMN IF NOT EXISTS sell_value_billion DECIMAL(12,2),
  ADD COLUMN IF NOT EXISTS net_value_billion DECIMAL(12,2),
  ADD COLUMN IF NOT EXISTS ownership_pct DECIMAL(5,2),
  ADD COLUMN IF NOT EXISTS remaining_room INTEGER;
