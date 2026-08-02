"""Shared helpers for broker domain modules.

New multi-ticker tools must call a true batch API in the shared layer —
never fan out per-ticker here. `gather_per_ticker` was removed in the
2026-04-12 optimization to enforce this architecturally.
"""

from collections.abc import Awaitable, Callable


async def cached_tool_call[T](
    cache: dict | None,
    key: str,
    factory: Callable[[], Awaitable[T]],
) -> T:
    """Check cache before running a tool coroutine. Store result on miss.

    `factory` is a zero-arg callable that returns the coroutine. This lets
    callers skip construction entirely on cache hits — passing a bare
    coroutine would leak it as an unawaited `RuntimeWarning`.
    """
    if cache is not None and key in cache:
        return cache[key]
    result = await factory()
    if cache is not None:
        cache[key] = result
    return result


def batch_cache_key(tool_name: str, tickers: list[str], *extras: object) -> str:
    """Build a deterministic cache key for a per-ticker batch tool.

    Tickers are upper-cased + sorted so cache hits are order- and
    case-insensitive. Trailing `extras` (scan_date, days_back, etc.) are
    appended with `:` separators.
    """
    ticker_part = ",".join(sorted(t.upper() for t in tickers))
    if not extras:
        return f"{tool_name}:{ticker_part}"
    extra_part = ":".join(str(e) for e in extras)
    return f"{tool_name}:{ticker_part}:{extra_part}"


def prose_formatter(result: object) -> str:
    """Extract prose from a dict result, fallback to str(result)."""
    if isinstance(result, dict):
        return result.get("prose") or str(result)
    return str(result)
