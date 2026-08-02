-- Migration 244: Add configurable HOLD loss threshold and max entry gap
--
-- RC2: HOLD win threshold hardcoded at -1.0% — too tight for VN stocks (2-3% daily vol)
-- RC3: Entry zones placed at nearest_support, often 5%+ below market — unreachable
--
-- hold_loss_threshold_pct: max day_change drop (%) before HOLD scores as loss (default 2.0)
-- max_entry_gap_pct: max gap (%) between close and entry before pullback tier activates (default 3.0)

ALTER TABLE trading_config
  ADD COLUMN IF NOT EXISTS hold_loss_threshold_pct DECIMAL(4,2) DEFAULT 2.0,
  ADD COLUMN IF NOT EXISTS max_entry_gap_pct DECIMAL(4,2) DEFAULT 3.0;
