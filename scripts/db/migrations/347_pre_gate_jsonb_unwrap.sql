-- Migration 347: backfill double-encoded JSONB in `pre_gate_candidates`.
--
-- The dffd0082 fleet sweep (migration 307) cleaned 8 columns whose writers
-- went through `scripts/shared/neon/*.py`, but `pre_gate_candidates` is
-- written by `scripts/eval/score_recorder.py` and was not in scope. Probe
-- on 2026-05-13 showed `jsonb_typeof(breakdown) = 'string'` AND
-- `jsonb_typeof(weights_jsonb) = 'string'` on every row (2026-04-28 .. 2026-05-12,
-- n=47) — the writer's `json_for_jsonb_cast(...)` paired with `$N::jsonb`
-- caused asyncpg's registered jsonb codec to double-encode.
--
-- Writer fix ships in the same commit (drop both wrappers + casts → codec
-- encodes once). This migration unwraps the legacy rows in place.
--
-- Idempotent: re-running has no effect once a row's type is correct.

BEGIN;

UPDATE pre_gate_candidates
SET breakdown = (breakdown #>> '{}')::jsonb
WHERE jsonb_typeof(breakdown) = 'string';

UPDATE pre_gate_candidates
SET weights_jsonb = (weights_jsonb #>> '{}')::jsonb
WHERE jsonb_typeof(weights_jsonb) = 'string';

-- Invariant: zero string-typed rows remain.
DO $$
DECLARE
    bad INT;
BEGIN
    SELECT COUNT(*) INTO bad
    FROM pre_gate_candidates
    WHERE jsonb_typeof(breakdown) = 'string'
       OR jsonb_typeof(weights_jsonb) = 'string';
    IF bad > 0 THEN
        RAISE EXCEPTION
            'migration 347 left % string-typed rows in pre_gate_candidates', bad;
    END IF;
END $$;

INSERT INTO schema_migrations (version)
VALUES ('347_pre_gate_jsonb_unwrap')
ON CONFLICT DO NOTHING;

COMMIT;
