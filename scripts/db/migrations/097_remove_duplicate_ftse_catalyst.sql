-- Migration 097: Remove duplicate FTSE ETF rebalancing catalyst
-- ftse_etf_rebalancing is redundant — covered by ftse_upgrade etf_rebalancing_prep phase
-- Date: 2026-02-22

DELETE FROM catalysts WHERE catalyst_key = 'ftse_etf_rebalancing';
