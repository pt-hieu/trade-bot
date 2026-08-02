-- 163_swing_max_loss_column.sql
-- DDL: Add swing max loss ceiling to trading_config (needs owner URL)
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS swing_max_loss_pct NUMERIC DEFAULT 7.0;
COMMENT ON COLUMN trading_config.swing_max_loss_pct IS 'Max loss % from entry before forced EXIT for SWING positions. LONGTERM uses longterm_catastrophic_pct instead.';
