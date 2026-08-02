-- Migration 074: Extend daily_technicals with vnstock_ta indicators
-- These are already computed by /technicals API but were previously discarded.
-- Storing them enables ML feature engineering and historical analysis.

ALTER TABLE daily_technicals
  ADD COLUMN IF NOT EXISTS atr DECIMAL(12,4),
  ADD COLUMN IF NOT EXISTS adx DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS adx_dmp DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS adx_dmn DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS bb_lower DECIMAL(12,4),
  ADD COLUMN IF NOT EXISTS bb_middle DECIMAL(12,4),
  ADD COLUMN IF NOT EXISTS bb_upper DECIMAL(12,4),
  ADD COLUMN IF NOT EXISTS bb_percent DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS bb_bandwidth DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS stoch_k DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS stoch_d DECIMAL(8,4),
  ADD COLUMN IF NOT EXISTS supertrend_direction VARCHAR(4),
  ADD COLUMN IF NOT EXISTS supertrend_value DECIMAL(12,4);

COMMENT ON COLUMN daily_technicals.atr IS 'Average True Range (14-period), raw VND scale';
COMMENT ON COLUMN daily_technicals.adx IS 'Average Directional Index (14): >25 strong trend';
COMMENT ON COLUMN daily_technicals.adx_dmp IS 'ADX DM+ (bullish pressure)';
COMMENT ON COLUMN daily_technicals.adx_dmn IS 'ADX DM- (bearish pressure)';
COMMENT ON COLUMN daily_technicals.bb_lower IS 'Bollinger Band lower (raw VND)';
COMMENT ON COLUMN daily_technicals.bb_middle IS 'Bollinger Band middle/SMA (raw VND)';
COMMENT ON COLUMN daily_technicals.bb_upper IS 'Bollinger Band upper (raw VND)';
COMMENT ON COLUMN daily_technicals.bb_percent IS 'BB %B: 0=at lower, 1=at upper band';
COMMENT ON COLUMN daily_technicals.bb_bandwidth IS 'BB bandwidth (volatility measure)';
COMMENT ON COLUMN daily_technicals.stoch_k IS 'Stochastic %K: <20 oversold, >80 overbought';
COMMENT ON COLUMN daily_technicals.stoch_d IS 'Stochastic %D (signal line)';
COMMENT ON COLUMN daily_technicals.supertrend_direction IS 'UP or DOWN';
COMMENT ON COLUMN daily_technicals.supertrend_value IS 'Supertrend level (raw VND)';
