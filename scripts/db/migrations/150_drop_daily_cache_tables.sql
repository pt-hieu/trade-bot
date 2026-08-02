-- Migration 150: Drop daily price/technicals cache tables
-- All consumers rerouted to vnstock API (Phases 1–2 of API-first migration).
-- Safe: IF EXISTS guards make this idempotent.

DROP MATERIALIZED VIEW IF EXISTS mv_relative_strength;
DROP VIEW IF EXISTS v_daily_returns;
DROP VIEW IF EXISTS v_latest_technicals;
-- v_portfolio_value_history depends on daily_prices (drop first)
-- Portfolio history chart returns empty snapshots until portfolio_snapshots table is built
DROP VIEW IF EXISTS v_portfolio_value_history;
DROP TABLE IF EXISTS daily_levels;
DROP TABLE IF EXISTS daily_technicals;
DROP TABLE IF EXISTS daily_prices;
