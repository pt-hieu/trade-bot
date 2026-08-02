"""VN-listed ticker universe — authoritative post-filter for LLM ticker extraction.

Loaded from the union of ``company_profiles`` and ``stocks`` (active only),
filtered through :func:`shared.ticker_extract.is_valid_ticker` so obvious
noise rows ("PROSE", "HOLDINGS", "FUEVFVND", "null") never enter the set.

Usage pattern (see AUDIT-2026-04-24-001 / ISSUE-2026-04-24-005):
    universe = await load_vn_universe_async()
    # pass ``universe`` into sync functions via parameter; or read the
    # module cache via ``get_cached_vn_universe()`` for threads spawned
    # after the async primer ran.

Fail-open guard: when the loaded universe is under
``VN_UNIVERSE_MIN_SIZE`` we raise ``VNUniverseUnavailable`` rather than
silently rejecting every ticker — an empty universe would otherwise look
like "the LLM hallucinated everything" and starve the news pipeline.
"""

from __future__ import annotations

import logging
import time
from threading import Lock

import logfire

from .ticker_extract import is_valid_ticker

logger = logging.getLogger(__name__)

VN_UNIVERSE_CACHE_TTL_SECONDS = 300
# Fail-open floor. Production company_profiles + stocks currently yields ~80
# valid tickers; anything materially smaller means the DB is misconfigured
# or a migration truncated a table.
VN_UNIVERSE_MIN_SIZE = 20

# Sentinel used across articles.affected_tickers, catalysts.affected_tickers,
# and agent prompts to mark "this event affects the Vietnamese market broadly,
# no specific ticker list". One typo would silently break the macro-blanket
# fan-out, so every consumer imports this constant.
VN_INDEX_PLACEHOLDER = "VN-INDEX"

_cached_universe: frozenset[str] | None = None
_cached_at_monotonic: float = 0.0
_cache_lock = Lock()


class VNUniverseUnavailable(RuntimeError):
    """Raised when the VN ticker universe cannot be loaded or is suspiciously small."""


def _cache_fresh(now: float) -> bool:
    return (
        _cached_universe is not None
        and (now - _cached_at_monotonic) < VN_UNIVERSE_CACHE_TTL_SECONDS
    )


async def load_vn_universe_async(force: bool = False) -> frozenset[str]:
    """Fetch VN universe from Neon; populate module cache.

    Call once from the pipeline orchestrator before any sync ticker work.
    """
    global _cached_universe, _cached_at_monotonic

    now = time.monotonic()
    with _cache_lock:
        if not force and _cache_fresh(now):
            assert _cached_universe is not None  # narrowed by _cache_fresh
            return _cached_universe

    from .database import fetch_all

    rows = await fetch_all(
        """
        SELECT ticker FROM company_profiles
        UNION
        SELECT ticker FROM stocks WHERE is_active = TRUE
        """
    )
    tickers = frozenset(
        row["ticker"] for row in rows if row.get("ticker") and is_valid_ticker(row["ticker"])
    )

    if len(tickers) < VN_UNIVERSE_MIN_SIZE:
        raise VNUniverseUnavailable(
            f"VN ticker universe too small ({len(tickers)} < {VN_UNIVERSE_MIN_SIZE}) — "
            "company_profiles / stocks may be mis-seeded; aborting news run"
        )

    with _cache_lock:
        _cached_universe = tickers
        _cached_at_monotonic = time.monotonic()

    logger.info("VN universe loaded: %d tickers", len(tickers))
    return tickers


def get_cached_vn_universe() -> frozenset[str]:
    """Return the primed universe — callable from threads that have no event loop.

    Raises ``VNUniverseUnavailable`` if the async primer hasn't run yet.
    """
    now = time.monotonic()
    with _cache_lock:
        if _cache_fresh(now):
            assert _cached_universe is not None
            return _cached_universe
    raise VNUniverseUnavailable(
        "VN universe cache empty — call load_vn_universe_async() before "
        "invoking sync ticker helpers."
    )


def load_vn_universe_sync() -> frozenset[str]:
    """Sync alias for ``get_cached_vn_universe`` — sync callers must pre-prime."""
    return get_cached_vn_universe()


def is_vn_listed(ticker: str | None, universe: frozenset[str] | None = None) -> bool:
    """True when ``ticker`` passes shape + universe membership checks.

    None-safe: a ``None`` or empty ticker returns False immediately. Layered
    on top of :func:`shared.ticker_extract.is_valid_ticker` so the cheap
    regex reject fires first; only shape-valid tickers consult the
    (pre-loaded) VN universe. ``VN_INDEX_PLACEHOLDER`` always passes.
    """
    if not ticker:
        return False
    if ticker == VN_INDEX_PLACEHOLDER:
        return True
    if not is_valid_ticker(ticker):
        return False
    if universe is None:
        universe = get_cached_vn_universe()
    return ticker in universe


def filter_vn_tickers(raw: list[str], *, context: str) -> list[str]:
    """Shared VN-universe post-pass used by every agent that outputs tickers.

    Accepts ``VN-INDEX`` verbatim, drops shape-invalid or off-universe tokens,
    logs the drops under ``context`` so callers don't each reimplement the
    filter (AUDIT-2026-04-24-001 / ISSUE-2026-04-24-005).
    """
    try:
        universe = get_cached_vn_universe()
    except VNUniverseUnavailable:
        logger.warning(
            "filter_vn_tickers(%s): cache empty — falling back to shape-only filter", context
        )
        return [str(t).upper() for t in raw if t and is_valid_ticker(str(t))]

    accepted: list[str] = []
    dropped: list[str] = []
    for entry in raw:
        if not entry:
            continue
        ticker = str(entry).upper()
        if is_vn_listed(ticker, universe):
            accepted.append(ticker)
        else:
            dropped.append(ticker)
    if dropped:
        logger.info("filter_vn_tickers(%s) dropped non-VN: %s", context, dropped[:10])
    return accepted


def filter_vn_only(
    raw: list[str] | None,
    universe: frozenset[str] | None,
    *,
    context: str,
) -> list[str]:
    """Universe-explicit variant of :func:`filter_vn_tickers`.

    Used by writer call sites that load the universe once at the orchestrator
    boundary and pass it through (avoids N×load fanout). ``VN_INDEX_PLACEHOLDER``
    always passes. Logs dropped tags at INFO under ``context``.

    Fail-CLOSED when ``universe`` is None (SWI-193): drop everything and
    alert. The universe IS the allowlist; shape-only validation accepts
    non-VN 3-letter codes (BOJ, ECB, OPEC, …) that leak into persistent
    narrative state. A cache miss is rare and recoverable on next call;
    accepting bad tickers is not.
    """
    if not raw:
        return []
    if universe is None:
        logfire.warning(
            "filter_vn_only_fail_closed",
            context=context,
            dropped_count=len(raw),
            sample=list(raw)[:10],
        )
        return []
    accepted: list[str] = []
    dropped: list[str] = []
    for entry in raw:
        if not entry:
            continue
        ticker = str(entry).upper()
        if ticker == VN_INDEX_PLACEHOLDER:
            accepted.append(ticker)
            continue
        if not is_valid_ticker(ticker):
            dropped.append(ticker)
            continue
        if ticker in universe:
            accepted.append(ticker)
        else:
            dropped.append(ticker)
    if dropped:
        logger.info("filter_vn_only(%s) dropped non-VN: %s", context, dropped[:10])
    return accepted


def reset_vn_universe_cache() -> None:
    """Reset the module cache — test-only hook."""
    global _cached_universe, _cached_at_monotonic
    with _cache_lock:
        _cached_universe = None
        _cached_at_monotonic = 0.0
