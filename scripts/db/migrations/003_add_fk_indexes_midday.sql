-- Migration: 003_add_fk_indexes_midday.sql
-- Description: Add missing FK indexes on midday check child tables
-- Impact: HIGH - Required for JOIN performance on midday_checks relationships

-- midday_entries_hit: FK to midday_checks(id)
CREATE INDEX IF NOT EXISTS idx_midday_entries_midday_id
    ON midday_entries_hit(midday_id);

-- midday_big_movers: FK to midday_checks(id)
CREATE INDEX IF NOT EXISTS idx_midday_big_movers_midday_id
    ON midday_big_movers(midday_id);

-- midday_position_alerts: FK to midday_checks(id)
CREATE INDEX IF NOT EXISTS idx_midday_position_alerts_midday_id
    ON midday_position_alerts(midday_id);

-- foreign_flow_details: FK to foreign_flows(id)
CREATE INDEX IF NOT EXISTS idx_foreign_flow_details_flow_id
    ON foreign_flow_details(flow_id);
