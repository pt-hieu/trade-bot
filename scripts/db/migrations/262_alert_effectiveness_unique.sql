-- Migration 262: Add unique constraint on alert_effectiveness to prevent duplicate rows.
-- Both web-side (linkTradeToAlert) and retro-side (match_trades_to_alerts) can insert
-- for the same alert+trade pair. Without this constraint, ON CONFLICT is a no-op.

-- Clean up existing duplicates (keep lowest id per group)
DELETE FROM alert_effectiveness
WHERE id NOT IN (
    SELECT MIN(id) FROM alert_effectiveness
    GROUP BY alert_id, COALESCE(trade_id, '00000000-0000-0000-0000-000000000000'::uuid)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_effectiveness_alert_trade
    ON alert_effectiveness (alert_id, trade_id)
    WHERE trade_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_effectiveness_alert_unconverted
    ON alert_effectiveness (alert_id)
    WHERE trade_id IS NULL;
