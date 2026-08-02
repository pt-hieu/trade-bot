-- Migration 202: Drop backtest_results table (LightGBM pipeline remnant)
-- The backtest infrastructure was part of the ML prediction pipeline removed in aaaa94c.
-- Table has 0 rows and scripts/backtest.py has been deleted.

DROP TABLE IF EXISTS backtest_results CASCADE;
