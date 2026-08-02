-- Migration 315: Add gate_decision_json column to daily_records
--
-- Persists the `RecommendationGateDecision` produced by
-- `scripts/shared/rules/recommendation_gate.py:compose_recommendation_gate`
-- so post-hoc SQL audit can show exactly which rules fired to produce a
-- given day's effective R:R floor, max_new_entries, and entries_allowed.
--
-- Blob shape (matches RecommendationGateDecision.to_jsonb()):
--   {
--     "effective_rr_floor": 2.5,
--     "max_new_entries": 3,
--     "entries_allowed": true,
--     "entries_blocked_reason": null,
--     "applied_rules": ["base_floor", "regime_boost_elevated_shock_only", ...],
--     "inputs_digest": {...}
--   }

BEGIN;

ALTER TABLE daily_records
    ADD COLUMN IF NOT EXISTS gate_decision_json JSONB;

COMMENT ON COLUMN daily_records.gate_decision_json IS
    'Serialized RecommendationGateDecision (see shared/rules/recommendation_gate.py). '
    'Single source of truth for the effective R:R floor, max new entries, '
    'and entries_allowed used to produce the brief and validate recommendations.';

COMMIT;
