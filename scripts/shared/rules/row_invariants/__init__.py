"""Python mirrors of Postgres CHECK constraints on pipeline-written tables (SWI-NN).

Each submodule mirrors the CHECK constraints of one table so producer-side
violations surface BEFORE `executemany` hits Postgres — a single bad row no
longer rolls back the entire batch (the 2026-05-07 0-rec wipeout vector).

Contract:
    validate_row(row: tuple) -> list[ViolationDetail]
        Empty list when the row passes every mirrored CHECK. Each ViolationDetail
        names the constraint and optionally carries a coercion callable. Callers
        apply coercions in order then re-validate once; remaining violations
        raise RowInvariantError.

Adding a CHECK to a pipeline-written table requires a matching update to the
table's mirror submodule + `CHECKS_MIRRORED` entry. The pre-commit hook
`check_migration_invariant_mirror.py` enforces this discipline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import (
    catalyst_signals,
    daily_evaluations,
    daily_recommendations,
    daily_records,
    morning_position_alerts,
)


class RowInvariantError(RuntimeError):
    """Raised when a row violates a CHECK that cannot be coerced."""


@dataclass(frozen=True)
class ViolationDetail:
    constraint_name: str
    suggested_coercion: Callable[[tuple], tuple] | None


CHECKS_MIRRORED: dict[str, set[str]] = {
    "daily_recommendations": {
        "daily_recs_plan_shape_action_chk",
        "daily_recs_plan_shape_chk",
        "daily_recommendations_plan_type_check",
    },
    "daily_evaluations": {
        "daily_evaluations_rule_applied_check",
        "daily_evaluations_stop_price_vnd_check",
    },
    "morning_position_alerts": set(),
    "catalyst_signals": set(),
    "daily_records": set(),
}


__all__ = [
    "CHECKS_MIRRORED",
    "RowInvariantError",
    "ViolationDetail",
    "catalyst_signals",
    "daily_evaluations",
    "daily_recommendations",
    "daily_records",
    "morning_position_alerts",
]
