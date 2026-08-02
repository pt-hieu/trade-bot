-- Migration 061: Trailing stops persistence table
-- Prevents stop regression by storing high-water mark for each position.
-- Updated each morning after computing stops — only ratchets up, never down.

CREATE TABLE IF NOT EXISTS trailing_stops (
    ticker VARCHAR(10) NOT NULL,
    stop_level NUMERIC(12,1),
    stop_type VARCHAR(30),
    updated_at DATE NOT NULL,
    PRIMARY KEY (ticker)
);

COMMENT ON TABLE trailing_stops IS 'High-water mark trailing stops for swing positions. Never moves down. Writes stops for all live positions regardless of settlement. Readers must apply shared.rules.settlement.is_sellable before acting on a stop. Stale stops for CLOSED trades are tolerated; readers skip them via the "no OPEN trade" log branch.';
