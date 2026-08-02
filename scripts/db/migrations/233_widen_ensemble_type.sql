-- Widen ensemble_type from VARCHAR(20) to VARCHAR(50)
-- "deterministic_positions" (24 chars) exceeds VARCHAR(20)
-- Must drop/recreate dependent view first

DROP VIEW IF EXISTS v_agent_belief_accuracy;

ALTER TABLE agent_beliefs
    ALTER COLUMN ensemble_type TYPE VARCHAR(50);

CREATE OR REPLACE VIEW v_agent_belief_accuracy AS
SELECT agent_key,
    ensemble_type,
    count(*) FILTER (WHERE brier_score IS NOT NULL) AS scored_beliefs,
    round(avg(brier_score) FILTER (WHERE brier_score IS NOT NULL), 4) AS avg_brier,
    round(avg(brier_score) FILTER (WHERE brier_score IS NOT NULL AND record_date >= (CURRENT_DATE - 30)), 4) AS brier_30d,
    round(avg(
        CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END
    ) FILTER (WHERE direction_correct IS NOT NULL), 3) AS direction_accuracy,
    round(avg(conviction), 3) AS avg_conviction,
    round(avg(days_held) FILTER (WHERE belief_status::text <> 'NEW'::text), 1) AS avg_streak_length,
    count(*) FILTER (WHERE belief_status::text = 'REVERSED'::text) AS reversals,
    round(avg(
        CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END
    ) FILTER (WHERE days_held >= 3 AND direction_correct IS NOT NULL), 3) AS accuracy_streak_3plus,
    round(avg(
        CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END
    ) FILTER (WHERE days_held = 1 AND direction_correct IS NOT NULL), 3) AS accuracy_fresh_beliefs
FROM agent_beliefs
GROUP BY agent_key, ensemble_type;
