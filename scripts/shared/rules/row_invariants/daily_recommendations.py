"""Mirror of CHECK constraints on `daily_recommendations` (SWI-NN).

Mirrored constraints:
- `daily_recs_plan_shape_action_chk` (migration 342): plan_shape IS NULL OR
  plan_shape = 'NONE' OR (action IN ('WATCH','WAIT') AND trigger_price_vnd IS NOT NULL).
- `daily_recs_plan_shape_chk` (migration 342): plan_shape IS NULL OR plan_shape
  IN canonical set.
- `daily_recommendations_plan_type_check` (migration 317): plan_type IN
  ('SWING','LONGTERM').

Row tuple layout matches `_INSERT_REC_SQL` ($1..$31 columns) — see
`shared.neon.insert_records._common._build_rec_row`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.rules.plan_shape import PLAN_SHAPE_VALUES

if TYPE_CHECKING:
    from . import ViolationDetail


_ACTION_IDX = 2
_PLAN_TYPE_IDX = 25
_TRIGGER_IDX = 26
_PLAN_SHAPE_IDX = 27

_WATCH_WAIT = frozenset({"WATCH", "WAIT"})
# Mirrors `daily_recommendations_plan_type_check` (migration 317). Kept local
# rather than imported from `_common._VALID_PLAN_TYPES` so `shared.rules.*` has
# no upward dependency on `shared.neon.*` (CLAUDE.md Tier-1 purity).
_VALID_PLAN_TYPES = frozenset({"SWING", "LONGTERM"})


def _coerce_plan_shape_to_none(row: tuple) -> tuple:
    out = list(row)
    out[_PLAN_SHAPE_IDX] = "NONE"
    return tuple(out)


def _coerce_plan_type_to_swing(row: tuple) -> tuple:
    out = list(row)
    out[_PLAN_TYPE_IDX] = "SWING"
    return tuple(out)


def validate_row(row: tuple) -> list[ViolationDetail]:
    """Return list of CHECK violations on this row tuple."""
    from . import ViolationDetail

    violations: list[ViolationDetail] = []
    action = row[_ACTION_IDX]
    plan_type = row[_PLAN_TYPE_IDX]
    trigger_vnd = row[_TRIGGER_IDX]
    plan_shape = row[_PLAN_SHAPE_IDX]

    action_upper = action.upper() if isinstance(action, str) else None
    shape_upper = plan_shape.upper() if isinstance(plan_shape, str) else plan_shape

    if shape_upper not in (None, "NONE") and shape_upper not in PLAN_SHAPE_VALUES:
        violations.append(
            ViolationDetail(
                constraint_name="daily_recs_plan_shape_chk",
                suggested_coercion=_coerce_plan_shape_to_none,
            )
        )

    if shape_upper not in (None, "NONE") and (action_upper not in _WATCH_WAIT or not trigger_vnd):
        violations.append(
            ViolationDetail(
                constraint_name="daily_recs_plan_shape_action_chk",
                suggested_coercion=_coerce_plan_shape_to_none,
            )
        )

    if not (isinstance(plan_type, str) and plan_type.upper() in _VALID_PLAN_TYPES):
        violations.append(
            ViolationDetail(
                constraint_name="daily_recommendations_plan_type_check",
                suggested_coercion=_coerce_plan_type_to_swing,
            )
        )

    return violations
