"""Generic sync wrapper factory for async database functions."""

import asyncio
import functools
from collections.abc import Callable, Coroutine
from typing import Any


def make_sync[R, **P](async_fn: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, R]:
    """Create a sync wrapper that runs async_fn then closes the db pool.

    Usage:
        get_swing_watchlist_sync = make_sync(get_swing_watchlist)
    """

    @functools.wraps(async_fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async def _run() -> R:
            from ..database import close_db

            try:
                return await async_fn(*args, **kwargs)
            finally:
                await close_db()

        return asyncio.run(_run())

    wrapper.__name__ = f"{async_fn.__name__}_sync"
    wrapper.__qualname__ = f"{async_fn.__qualname__}_sync"
    return wrapper
