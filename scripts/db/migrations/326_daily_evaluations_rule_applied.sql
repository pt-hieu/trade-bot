-- Migration 326: Add rule_applied to daily_evaluations (2026-04-22, MON-2026-04-22-007).
--
-- The LLM retro commentary keeps qualitative `analysis` free-text, but the
-- deterministic rule label now comes from a Python post-pass
-- (`shared/rules/retro_rule_classifier.py::classify_retro_rule`) so bundle-
-- side auditors can group outcomes by rule without keyword-scanning prose.
-- First instance of this pattern — mirrors `catalysts.catalyst_type` →
-- `catalyst_classifier` introduced 2026-04-21.

BEGIN;

ALTER TABLE daily_evaluations
    ADD COLUMN IF NOT EXISTS rule_applied TEXT;

-- Allowed vocabulary (must stay in lock-step with
-- shared/rules/retro_rule_classifier.RetroRule). Validated via CHECK
-- constraint — narrower than a free text column but friendlier to
-- additive migrations than a native ENUM.
ALTER TABLE daily_evaluations
    DROP CONSTRAINT IF EXISTS daily_evaluations_rule_applied_check;

ALTER TABLE daily_evaluations
    ADD CONSTRAINT daily_evaluations_rule_applied_check
    CHECK (
        rule_applied IS NULL OR rule_applied IN (
            'SWING_TARGET_HIT',
            'SWING_STOPPED',
            'SWING_WIN',
            'SWING_LOSS',
            'SWING_PENDING',
            'SWING_MISSED',
            'SWING_HOLD',
            'LONGTERM_CATASTROPHIC',
            'LONGTERM_THESIS_INTACT',
            'LONGTERM_EXCLUDED',
            'WATCH_MISS',
            'WAIT_UNMET',
            'SKIP_CORRECT',
            'TRADE_EXECUTED_WIN',
            'TRADE_EXECUTED_LOSS',
            'UNCLASSIFIED'
        )
    );

COMMIT;
