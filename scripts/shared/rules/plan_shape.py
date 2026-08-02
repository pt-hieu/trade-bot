"""Single source of truth for valid PlanShape labels + invariant rule.

SQL mirror: scripts/db/migrations/342_conditional_plan_fields.sql CHECK
constraint on daily_recommendations.plan_shape + plan_shape_action invariant.
Keep in lockstep — adding a new shape requires a SWI-NN migration to extend
the CHECK constraint.
"""

from __future__ import annotations

import logging
from typing import Literal

from shared.env import is_production

logger = logging.getLogger(__name__)


type PlanShape = Literal["BREAKOUT", "PULLBACK", "TREND_PULLBACK", "BOUNCE", "MEAN_REVERT", "NONE"]

PLAN_SHAPE_VALUES: frozenset[str] = frozenset(
    {"BREAKOUT", "PULLBACK", "TREND_PULLBACK", "BOUNCE", "MEAN_REVERT", "NONE"}
)

_WATCH_WAIT_ACTIONS: frozenset[str] = frozenset({"WATCH", "WAIT"})


def coerce_plan_shape_for_check(
    plan_shape: str | None,
    action: str | None,
    trigger_vnd: int | None,
    *,
    strict: bool | None = None,
) -> str | None:
    """Apply `daily_recs_plan_shape_action_chk` Python-side (SWI-NN).

    The DB CHECK requires::

        plan_shape IS NULL OR plan_shape = 'NONE' OR
        (action IN ('WATCH','WAIT') AND trigger_price_vnd IS NOT NULL)

    A non-NONE plan_shape on a BUY/HOLD row, or on a WATCH row without a
    trigger price, fails the CHECK and rolls back the whole asyncpg
    `executemany` batch — the 2026-05-07 0-rec wipeout vector.

    `strict=None` reads `SWINGY_ENV`: production → coerce silently (return
    'NONE') + log_warn; anything else (dev, CI, unset) → raise AssertionError
    so producer-side bugs surface in tests. Pass `strict=True/False` to
    override the env gate.
    """
    if strict is None:
        strict = not is_production()

    if plan_shape is None:
        return None
    shape_upper = plan_shape.upper() if isinstance(plan_shape, str) else None
    if shape_upper in (None, "NONE"):
        return "NONE" if shape_upper == "NONE" else None

    action_upper = action.upper() if isinstance(action, str) else None
    if action_upper in _WATCH_WAIT_ACTIONS and trigger_vnd:
        return shape_upper

    # Invariant violated — non-NONE shape without WATCH/WAIT + trigger.
    if strict:
        raise AssertionError(
            f"plan_shape={shape_upper!r} requires action IN (WATCH,WAIT) "
            f"AND trigger_price_vnd populated. Got action={action_upper!r} "
            f"trigger_vnd={trigger_vnd!r}. Violates "
            "daily_recs_plan_shape_action_chk (migration 342)."
        )

    try:
        from shared.observability import log_warn

        log_warn(
            "plan_shape_coerced",
            scope="coerce_plan_shape_for_check",
            original_shape=shape_upper,
            action=action_upper,
            trigger_vnd=trigger_vnd,
        )
    except Exception:
        pass
    logger.warning(
        "plan_shape=%s coerced to NONE: action=%s trigger_vnd=%s",
        shape_upper,
        action_upper,
        trigger_vnd,
    )
    return "NONE"
