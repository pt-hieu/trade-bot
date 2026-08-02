"""Tests for shared.rules.row_invariants — Python mirrors of DB CHECK constraints (SWI-NN).

Each table module mirrors every CHECK on its DB counterpart so producer-side
violations surface before the executemany hits Postgres. ViolationDetail.suggested_coercion
is a pure callable that rewrites the row tuple; callers re-validate once after
applying coercions.
"""

from __future__ import annotations

import numpy as np
import pytest

from shared.rules.row_invariants import (
    CHECKS_MIRRORED,
    ViolationDetail,
    daily_evaluations,
    daily_recommendations,
)
from shared.rules.row_invariants.eval_columns import (
    EVAL_COLUMNS,
    STOP_PRICE_VND_IDX,
    TICKER_IDX,
)

# Column index in _INSERT_REC_SQL tuple (0-based, matches _common._build_rec_row return)
REC_TICKER = 1
REC_ACTION = 2
REC_PLAN_TYPE = 25
REC_TRIGGER = 26
REC_PLAN_SHAPE = 27


def _make_rec_row(
    *,
    ticker: str = "FPT",
    action: str = "WATCH",
    plan_type: str = "SWING",
    trigger_vnd: int | None = 50000,
    plan_shape: str | None = "BREAKOUT",
) -> tuple[object, ...]:
    """Build a 31-tuple matching _build_rec_row's output for testing."""
    row = [None] * 31
    row[0] = 1  # record_id
    row[REC_TICKER] = ticker
    row[REC_ACTION] = action
    row[REC_PLAN_TYPE] = plan_type
    row[REC_TRIGGER] = trigger_vnd
    row[REC_PLAN_SHAPE] = plan_shape
    return tuple(row)


class TestDailyRecommendationsValidate:
    """Mirror of daily_recs_plan_shape_action_chk + plan_shape_chk + plan_type_chk."""

    def test_valid_watch_with_shape_and_trigger(self):
        row = _make_rec_row(action="WATCH", plan_shape="BREAKOUT", trigger_vnd=50000)
        assert daily_recommendations.validate_row(row) == []

    def test_buy_with_shape_violates_action_chk(self):
        row = _make_rec_row(action="BUY", plan_shape="BREAKOUT", trigger_vnd=None)
        violations = daily_recommendations.validate_row(row)
        names = {v.constraint_name for v in violations}
        assert "daily_recs_plan_shape_action_chk" in names

    def test_watch_without_trigger_violates_action_chk(self):
        row = _make_rec_row(action="WATCH", plan_shape="BREAKOUT", trigger_vnd=None)
        violations = daily_recommendations.validate_row(row)
        names = {v.constraint_name for v in violations}
        assert "daily_recs_plan_shape_action_chk" in names

    def test_invalid_plan_shape_value_violates_plan_shape_chk(self):
        row = _make_rec_row(plan_shape="NOT_A_REAL_SHAPE", action="WATCH", trigger_vnd=50000)
        violations = daily_recommendations.validate_row(row)
        names = {v.constraint_name for v in violations}
        assert "daily_recs_plan_shape_chk" in names

    def test_invalid_plan_type_violates_plan_type_chk(self):
        row = _make_rec_row(plan_type="UNKNOWN")
        violations = daily_recommendations.validate_row(row)
        names = {v.constraint_name for v in violations}
        assert "daily_recommendations_plan_type_check" in names

    def test_none_plan_shape_passes(self):
        row = _make_rec_row(plan_shape=None, action="BUY", trigger_vnd=None)
        assert daily_recommendations.validate_row(row) == []

    def test_none_literal_plan_shape_passes(self):
        row = _make_rec_row(plan_shape="NONE", action="BUY", trigger_vnd=None)
        assert daily_recommendations.validate_row(row) == []

    def test_coercion_fixes_action_chk(self):
        row = _make_rec_row(action="BUY", plan_shape="BREAKOUT", trigger_vnd=None)
        violations = daily_recommendations.validate_row(row)
        # Apply each suggested coercion in order
        for v in violations:
            if v.suggested_coercion is not None:
                row = v.suggested_coercion(row)
        # Re-validate — should now pass
        assert daily_recommendations.validate_row(row) == []


class TestDailyEvaluationsValidate:
    """Mirror of daily_evaluations_rule_applied_check (migration 326)."""

    def _make_eval_row(self, rule_applied: str | None = "SWING_WIN") -> tuple[object, ...]:
        row: list[object] = [None] * len(EVAL_COLUMNS)
        row[EVAL_COLUMNS.index("rule_applied")] = rule_applied
        return tuple(row)

    def test_valid_rule_applied_passes(self):
        row = self._make_eval_row("SWING_TARGET_HIT")
        assert daily_evaluations.validate_row(row) == []

    def test_null_rule_applied_passes(self):
        row = self._make_eval_row(None)
        assert daily_evaluations.validate_row(row) == []

    def test_unknown_rule_applied_violates(self):
        row = self._make_eval_row("MADE_UP_RULE")
        violations = daily_evaluations.validate_row(row)
        names = {v.constraint_name for v in violations}
        assert "daily_evaluations_rule_applied_check" in names

    def test_coercion_nulls_unknown_rule(self):
        row = self._make_eval_row("MADE_UP_RULE")
        for v in daily_evaluations.validate_row(row):
            if v.suggested_coercion is not None:
                row = v.suggested_coercion(row)
        assert daily_evaluations.validate_row(row) == []


class TestDailyEvaluationsStopPrice:
    """Mirror of daily_evaluations_stop_price_vnd_check (migration 333)."""

    def _make_eval_row(self, stop: object) -> tuple[object, ...]:
        row: list[object] = [None] * len(EVAL_COLUMNS)
        row[0] = 1
        row[TICKER_IDX] = "SAB"
        row[STOP_PRICE_VND_IDX] = stop
        return tuple(row)

    @pytest.mark.parametrize(
        "stop, expect_violation, case_id",
        [
            (None, False, "null_allowed"),
            (38, True, "sab_incident_value"),
            (999, True, "boundary_below_floor"),
            (1000, False, "boundary_at_floor"),
            (38000, False, "typical_vnd_value"),
            ("bogus", True, "non_numeric_string"),
            (True, True, "bool_rejected_even_though_int_subclass"),
            (np.int64(38000), False, "numpy_int_above_floor_passes"),
            (0, True, "stop_zero_defense_in_depth"),
        ],
    )
    def test_stop_threshold(self, stop, expect_violation, case_id):
        # NOTE: `stop_zero_defense_in_depth` exercises the invariant standalone.
        # The integrated path in _build_eval_row short-circuits 0 to None via
        # the `and stop_kvnd` truthy guard, so 0 can't reach the invariant in
        # production. The defensive case pins behaviour for future refactors.
        row = self._make_eval_row(stop)
        violations = daily_evaluations.validate_row(row)
        names = {v.constraint_name for v in violations}
        assert ("daily_evaluations_stop_price_vnd_check" in names) is expect_violation

    def test_coercion_nulls_subthreshold(self):
        row = self._make_eval_row(38)
        for v in daily_evaluations.validate_row(row):
            if v.suggested_coercion is not None:
                row = v.suggested_coercion(row)
        assert row[STOP_PRICE_VND_IDX] is None
        assert daily_evaluations.validate_row(row) == []


class TestBuildEvalRowStopZeroShortCircuit:
    """Integration: _build_eval_row passes stop_price=0 cleanly (no violation)."""

    def test_zero_stop_price_becomes_null_no_violation(self):
        from shared.neon.insert_records._common import _build_eval_row

        row = _build_eval_row(
            record_id=1,
            eval_data={
                "ticker": "SAB",
                "recommendation": "BUY",
                "stop_price": 0,
                "status": "MISSED",
                "section": "TOP_PICKS",
            },
        )
        assert row is not None
        assert row[STOP_PRICE_VND_IDX] is None


class TestRegistry:
    """CHECKS_MIRRORED is the source of truth the migration-mirror hook + integration test consult."""

    def test_registry_has_daily_recommendations(self):
        assert "daily_recommendations" in CHECKS_MIRRORED
        names = CHECKS_MIRRORED["daily_recommendations"]
        assert "daily_recs_plan_shape_action_chk" in names
        assert "daily_recs_plan_shape_chk" in names
        assert "daily_recommendations_plan_type_check" in names

    def test_registry_has_daily_evaluations(self):
        assert "daily_evaluations" in CHECKS_MIRRORED
        assert "daily_evaluations_rule_applied_check" in CHECKS_MIRRORED["daily_evaluations"]
        assert "daily_evaluations_stop_price_vnd_check" in CHECKS_MIRRORED["daily_evaluations"]

    def test_violation_detail_is_frozen(self):
        v = ViolationDetail(constraint_name="x", suggested_coercion=None)
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            v.constraint_name = "y"  # type: ignore[misc]


class TestEvalColumnsSqlParity:
    """EVAL_COLUMNS length matches INSERT_EVAL_SQL placeholder count.

    Replaces the runtime assert previously co-located with INSERT_EVAL_SQL so
    the check runs once in CI (not on every import) and survives `python -O`.
    """

    def test_placeholder_count_matches_eval_columns(self):
        import re

        from shared.neon.insert_records._common import INSERT_EVAL_SQL

        placeholders = re.findall(r"\$\d+", INSERT_EVAL_SQL)
        assert len(placeholders) == len(EVAL_COLUMNS)
