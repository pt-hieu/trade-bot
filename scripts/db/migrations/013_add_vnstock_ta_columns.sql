-- Migration 013: Add vnstock_ta technical indicators to daily_technicals
-- Date: 2026-02-02
-- Description: Adds columns for ATR, SUPERTREND, ADX, BBANDS, STOCH indicators

-- Create enum for supertrend direction (consistent with existing enum patterns)
-- Note: migration runner handles "already exists" errors gracefully
CREATE TYPE supertrend_dir AS ENUM ('UP', 'DOWN');

-- ATR (Average True Range) - for stop-loss sizing
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS atr DECIMAL(12, 4);

-- SUPERTREND - trend direction + dynamic support/resistance
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS supertrend_value DECIMAL(12, 4);
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS supertrend_direction supertrend_dir;
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS supertrend_lower DECIMAL(12, 4);
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS supertrend_upper DECIMAL(12, 4);

-- ADX (Average Directional Index) - trend strength measurement
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS adx DECIMAL(6, 2);
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS adx_dmp DECIMAL(6, 2);
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS adx_dmn DECIMAL(6, 2);

-- BBANDS (Bollinger Bands) - volatility indicator
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS bb_lower DECIMAL(12, 4);
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS bb_middle DECIMAL(12, 4);
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS bb_upper DECIMAL(12, 4);
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS bb_bandwidth DECIMAL(8, 4);
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS bb_percent DECIMAL(6, 4);

-- STOCH (Stochastic Oscillator) - momentum indicator
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS stoch_k DECIMAL(6, 2);
ALTER TABLE daily_technicals ADD COLUMN IF NOT EXISTS stoch_d DECIMAL(6, 2);

-- Add index on new columns that may be queried frequently
CREATE INDEX IF NOT EXISTS idx_tech_atr ON daily_technicals(atr);
CREATE INDEX IF NOT EXISTS idx_tech_adx ON daily_technicals(adx);
CREATE INDEX IF NOT EXISTS idx_tech_supertrend_dir ON daily_technicals(supertrend_direction);
