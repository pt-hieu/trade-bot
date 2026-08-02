-- Migration 126: Add outcome tracking and catalyst type to catalysts table
ALTER TABLE catalysts ADD COLUMN IF NOT EXISTS outcome_detail TEXT;
ALTER TABLE catalysts ADD COLUMN IF NOT EXISTS actual_impact VARCHAR(20);
ALTER TABLE catalysts ADD COLUMN IF NOT EXISTS pre_event_snapshot JSONB;
ALTER TABLE catalysts ADD COLUMN IF NOT EXISTS post_event_snapshot JSONB;
ALTER TABLE catalysts ADD COLUMN IF NOT EXISTS impact_score FLOAT;
ALTER TABLE catalysts ADD COLUMN IF NOT EXISTS catalyst_type VARCHAR(50) DEFAULT 'regulatory';

CREATE INDEX IF NOT EXISTS idx_catalysts_type
ON catalysts (catalyst_type) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_catalysts_completed
ON catalysts (status, actual_date DESC) WHERE status = 'completed';
