"""Mirror of CHECK constraints on `daily_evaluations` (SWI-NN).

Mirrored:
- `daily_evaluations_rule_applied_check` (migration 326): rule_applied IS NULL
  OR rule_applied IN <16 retro rule enum values>.
- `daily_evaluations_stop_price_vnd_check` (migration 333): stop_price_vnd IS
  NULL OR stop_price_vnd >= 1000. Sub-1000 non-NULL values almost always
  indicate a kVND→VND unit bug (e.g. SWI-140 `44.91` vs `44910`) — coerce
  to NULL + ERROR-log rather than rolling back the executemany batch.

Row tuple layout matches `INSERT_EVAL_SQL` ($1..$27) — see
`shared.neon.insert_records._common._build_eval_row`. Index constants live in
`shared.neon.insert_records._eval_columns` as a single source of truth.
"""

from __future__ import annotations

import logging
from numbers import Real
from typing import TYPE_CHECKING

from .eval_columns import (
    RULE_APPLIED_IDX as _RULE_APPLIED_IDX,
)
from .eval_columns import (
    STOP_PRICE_VND_IDX as _STOP_PRICE_VND_IDX,
)
from .eval_columns import (
    TICKER_IDX as _TICKER_IDX,
)

if TYPE_CHECKING:
    from . import ViolationDetail


logger = logging.getLogger(__name__)
_STOP_PRICE_FLOOR_VND = 1000  # mirror of migration 333:28-29

_VALID_RULES = frozenset(
    {
        "SWING_TARGET_HIT",
        "SWING_STOPPED",
        "SWING_WIN",
        "SWING_LOSS",
        "SWING_PENDING",
        "SWING_MISSED",
        "SWING_HOLD",
        "LONGTERM_CATASTROPHIC",
        "LONGTERM_THESIS_INTACT",
        "LONGTERM_EXCLUDED",
        "WATCH_MISS",
        "WAIT_UNMET",
        "SKIP_CORRECT",
        "TRADE_EXECUTED_WIN",
        "TRADE_EXECUTED_LOSS",
        "UNCLASSIFIED",
    }
)


def _coerce_rule_to_null(row: tuple) -> tuple:
    out = list(row)
    out[_RULE_APPLIED_IDX] = None
    return tuple(out)


def _coerce_stop_to_null(row: tuple) -> tuple:
    record_id = row[0] if row else None
    ticker = row[_TICKER_IDX] if len(row) > _TICKER_IDX else None
    raw = row[_STOP_PRICE_VND_IDX]
    logger.error(
        "stop_price_subthreshold_coerced "
        "record_id=%s ticker=%s stop_price_vnd=%r floor=%d "
        "constraint=daily_evaluations_stop_price_vnd_check",
        record_id,
        ticker,
        raw,
        _STOP_PRICE_FLOOR_VND,
    )
    out = list(row)
    out[_STOP_PRICE_VND_IDX] = None
    return tuple(out)


def validate_row(row: tuple) -> list[ViolationDetail]:
    from . import ViolationDetail

    violations: list[ViolationDetail] = []
    rule = row[_RULE_APPLIED_IDX]
    if rule is not None and (not isinstance(rule, str) or rule not in _VALID_RULES):
        violations.append(
            ViolationDetail(
                constraint_name="daily_evaluations_rule_applied_check",
                suggested_coercion=_coerce_rule_to_null,
            )
        )

    stop = row[_STOP_PRICE_VND_IDX]
    if stop is not None and (
        isinstance(stop, bool) or not isinstance(stop, Real) or stop < _STOP_PRICE_FLOOR_VND
    ):
        violations.append(
            ViolationDetail(
                constraint_name="daily_evaluations_stop_price_vnd_check",
                suggested_coercion=_coerce_stop_to_null,
            )
        )
    return violations
