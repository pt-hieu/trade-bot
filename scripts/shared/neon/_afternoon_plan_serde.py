"""Serialize midday ``afternoon_plan`` (migration 316) for JSONB INSERT.

Two writers — ``insert_midday_check`` and ``insert_daily_record.midday_data``
— accept the structured list form but must forward a JSON-serialised string
because the JSONB column uses ``$N::jsonb``. Legacy free-text values coerce
to a single NOTE entry so a retried resume path cannot regress to TEXT.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def serialize_afternoon_plan(raw: Any, *, context: str) -> str:
    """Return the JSON-string form expected by the midday JSONB columns.

    ``context`` is a short caller identifier used only in the warning
    emitted when a non-list value leaks through (indicates an upstream bug).
    """
    if isinstance(raw, list):
        return json.dumps([item for item in raw if isinstance(item, dict)])
    if raw is None:
        return json.dumps([])
    logger.warning(
        "%s: coercing non-list afternoon_plan (type=%s) to NOTE",
        context,
        type(raw).__name__,
    )
    return json.dumps(
        [
            {
                "ticker": None,
                "action": "NOTE",
                "confidence": "LOW",
                "reason": str(raw),
            }
        ]
    )
