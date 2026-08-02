-- Migration: 002_add_fk_indexes_learnings.sql
-- Description: Add missing FK indexes on learnings child tables
-- Impact: CRITICAL - Required for JOIN performance on daily_records relationships

-- daily_recommendations: FK to daily_records(id)
CREATE INDEX IF NOT EXISTS idx_daily_recommendations_record_id
    ON daily_recommendations(record_id);

-- daily_evaluations: FK to daily_records(id)
CREATE INDEX IF NOT EXISTS idx_daily_evaluations_record_id
    ON daily_evaluations(record_id);

-- mode_violations: FK to daily_records(id)
CREATE INDEX IF NOT EXISTS idx_mode_violations_record_id
    ON mode_violations(record_id);

-- rotation_sector_returns: FK to rotation_evaluations(id)
CREATE INDEX IF NOT EXISTS idx_rotation_sector_returns_eval_id
    ON rotation_sector_returns(rotation_eval_id);

-- sector_rotation_details: FK to sector_rotations(id)
CREATE INDEX IF NOT EXISTS idx_sector_rotation_details_rotation_id
    ON sector_rotation_details(rotation_id);

-- midday_data: FK to daily_records(id)
CREATE INDEX IF NOT EXISTS idx_midday_data_record_id
    ON midday_data(record_id);

-- midday_summaries: FK to daily_records(id)
CREATE INDEX IF NOT EXISTS idx_midday_summaries_record_id
    ON midday_summaries(record_id);

-- rotation_evaluations: FK to daily_records(id)
CREATE INDEX IF NOT EXISTS idx_rotation_evaluations_record_id
    ON rotation_evaluations(record_id);

-- macro_evaluations: FK to daily_records(id)
CREATE INDEX IF NOT EXISTS idx_macro_evaluations_record_id
    ON macro_evaluations(record_id);

-- macro_regime_accuracy: FK to macro_patterns(id)
CREATE INDEX IF NOT EXISTS idx_macro_regime_accuracy_pattern_id
    ON macro_regime_accuracy(pattern_id);

-- rotation_sector_scores: FK to rotation_patterns(id)
CREATE INDEX IF NOT EXISTS idx_rotation_sector_scores_pattern_id
    ON rotation_sector_scores(pattern_id);
