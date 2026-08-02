-- Migration 078: Add commodity + yield + regional market data to macro_metrics
-- Copper = industrial cycle proxy, Oil = energy sector driver
-- US 10Y yield = capital flow indicator, Shanghai = regional correlation

ALTER TABLE macro_metrics
  ADD COLUMN IF NOT EXISTS copper_price DECIMAL(10,4),
  ADD COLUMN IF NOT EXISTS copper_change_pct DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS oil_price DECIMAL(10,4),
  ADD COLUMN IF NOT EXISTS oil_change_pct DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS us_10y_yield DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS us_10y_change_pct DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS shanghai_close DECIMAL(12,4),
  ADD COLUMN IF NOT EXISTS shanghai_change_pct DECIMAL(8,4);

COMMENT ON COLUMN macro_metrics.copper_price IS 'Copper futures (HG=F) price USD/lb';
COMMENT ON COLUMN macro_metrics.copper_change_pct IS 'Copper 1-day change %';
COMMENT ON COLUMN macro_metrics.oil_price IS 'Crude oil (CL=F) price USD/barrel';
COMMENT ON COLUMN macro_metrics.oil_change_pct IS 'Oil 1-day change %';
COMMENT ON COLUMN macro_metrics.us_10y_yield IS 'US 10Y Treasury yield %';
COMMENT ON COLUMN macro_metrics.us_10y_change_pct IS 'US 10Y yield 1-day change %';
COMMENT ON COLUMN macro_metrics.shanghai_close IS 'Shanghai Composite (000001.SS) close';
COMMENT ON COLUMN macro_metrics.shanghai_change_pct IS 'Shanghai 1-day change %';
