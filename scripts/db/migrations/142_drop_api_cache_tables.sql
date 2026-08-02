-- Migration 142: Drop API cache tables
--
-- These tables were populated by pipeline scripts (fundamentals_sync.py,
-- enrich_flow.py, enrich_events.py) that cached raw vnstock API data.
-- All consumers now read directly from the vnstock API via shared.api.fundamentals
-- and shared.api.enrichment — the DB roundtrip is eliminated.
--
-- Tables dropped:
--   financial_statements  — replaced by /financials/statements
--   financial_ratios      — replaced by /financials/ratios
--   daily_flow            — replaced by /ticker/enrichment (flow+prop+orders)
--   insider_transactions  — replaced by /ticker/enrichment (insider)
--   corporate_events      — replaced by /ticker/enrichment (events)

DROP TABLE IF EXISTS financial_statements;
DROP TABLE IF EXISTS financial_ratios;
DROP TABLE IF EXISTS daily_flow;
DROP TABLE IF EXISTS insider_transactions;
DROP TABLE IF EXISTS corporate_events;
