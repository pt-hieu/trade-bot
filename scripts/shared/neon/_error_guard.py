"""Narrow-except helper for shared/neon DB writers.

Why this exists
---------------
Hot paths in ``shared/neon/`` historically ended every DB writer with::

    except Exception as e:
        logger.warning("...: %s", e)
        return False

That swallows pyright type errors, schema drift, key contract bugs, and
business-logic ``RuntimeError`` (the 2026-04-19 retro evaluator gap was
masked by exactly this pattern). Only true connectivity failures should
ever be downgraded to a warning + sentinel return — anything else must
propagate so the run dies loudly.

Usage
-----

    from shared.neon._error_guard import narrow_db_error

    try:
        ...
    except Exception as exc:
        narrow_db_error(exc, context="insert_daily_record")
        return False  # only reached for the connectivity allowlist

If the exception is not on the allowlist, ``narrow_db_error`` re-raises
it. Callers therefore never need to assemble their own re-raise logic.
"""

from __future__ import annotations

import logging
from typing import Final

import asyncpg

logger = logging.getLogger(__name__)

# Connectivity-only allowlist. Anything outside this tuple propagates so
# the pipeline dies on real bugs (KeyError, ValueError, RuntimeError, etc.).
_SWALLOWABLE: Final[tuple[type[BaseException], ...]] = (
    asyncpg.PostgresConnectionError,
    asyncpg.InterfaceError,
    TimeoutError,
)


def narrow_db_error(exc: BaseException, *, context: str) -> None:
    """Log + swallow connectivity errors only; re-raise everything else.

    `context` is a short string identifying the call site (e.g.
    ``"insert_daily_record"``). It is included in the warning message so
    grep on a known prefix surfaces the swallowed errors.
    """
    if isinstance(exc, _SWALLOWABLE):
        logger.warning("%s connectivity error: %s", context, exc)
        return
    raise exc
