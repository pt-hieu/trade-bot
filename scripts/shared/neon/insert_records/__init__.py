"""insert_records package — preserves the pre-split public API.

Import surface is identical to the former `insert_records.py` module so every
existing consumer in `shared/neon/__init__.py` and `tests/unit/test_insert_records.py`
keeps working unchanged. Private helpers (`_normalize_trading_mode`,
`_is_valid_ticker`) are also re-exported so the test suite's direct imports
resolve against the package root.
"""

from ._common import (
    _INSERT_REC_SQL,
    INSERT_EVAL_SQL,
    _build_eval_row,
    _build_rec_row,
    _is_valid_ticker,
    _normalize_action,
    _normalize_trading_mode,
    _vnd_int,
)
from .alert_fire import insert_alert_fire_recommendation
from .continuity import update_previous_day_change, update_previous_day_change_sync
from .daily import insert_daily_record, insert_daily_record_sync
from .morning import (
    get_morning_recommendations,
    get_morning_recommendations_sync,
    insert_morning_recommendations,
    insert_morning_recommendations_sync,
)
from .votes import insert_ensemble_votes

__all__ = [
    "INSERT_EVAL_SQL",
    "_INSERT_REC_SQL",
    "_build_eval_row",
    "_build_rec_row",
    "_is_valid_ticker",
    "_normalize_action",
    "_normalize_trading_mode",
    "_vnd_int",
    "get_morning_recommendations",
    "get_morning_recommendations_sync",
    "insert_alert_fire_recommendation",
    "insert_daily_record",
    "insert_daily_record_sync",
    "insert_ensemble_votes",
    "insert_morning_recommendations",
    "insert_morning_recommendations_sync",
    "update_previous_day_change",
    "update_previous_day_change_sync",
]
