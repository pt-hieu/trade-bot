"""Anchor ticker list for LLM prompt injection (Tier 1 of the news pipeline).

The LLM's training-time knowledge of the VN market is stale + US-biased, so
asking "which tickers does this article mention" drifts toward US codes
(IBM, KMI, PSX) or abbreviation guesses (UAE, XIV, WHR). The anchor list
ports the VN universe into-context cheaply — small enough to fit in every
prompt, broad enough to cover the tickers news actually mentions.

Composition: VN30 ∪ swing_watchlist ∪ portfolio_holdings, deduped + sorted.
Designed to stay around 60-90 tickers; the full universe stays server-side
for the post-LLM intersection (shared.vn_universe).
"""

from __future__ import annotations

import asyncio
import logging
import time
from threading import Lock

logger = logging.getLogger(__name__)

ANCHOR_MAX_SIZE = 90
ANCHOR_CACHE_TTL_SECONDS = 300

_cached_anchor: list[str] | None = None
_cached_prompt_header: str | None = None
_cached_at_monotonic: float = 0.0
_cache_lock = Lock()


def build_anchor_tickers(
    watchlist: dict[str, list[str]] | None,
    holdings: list[dict] | None,
    extra: set[str] | None = None,
) -> list[str]:
    """Return the anchor list as a deterministic sorted list.

    Uses the static VN30 + extras list as a floor so the anchor is stable
    across runs even when the watchlist is empty.
    """
    from agents.watchlist_update import VN30_TICKERS

    anchor: set[str] = set(VN30_TICKERS)
    if watchlist:
        for tickers in watchlist.values():
            anchor.update(tickers)
    if holdings:
        for holding in holdings:
            ticker = holding.get("ticker")
            if ticker:
                anchor.add(str(ticker))
    if extra:
        anchor.update(extra)

    sorted_anchor = sorted(anchor)
    if len(sorted_anchor) > ANCHOR_MAX_SIZE:
        logger.info("Anchor ticker list truncated %d -> %d", len(sorted_anchor), ANCHOR_MAX_SIZE)
        sorted_anchor = sorted_anchor[:ANCHOR_MAX_SIZE]
    return sorted_anchor


async def build_anchor_tickers_async() -> list[str]:
    """Convenience: load watchlist + holdings via the async DB layer, build anchor.

    The 5-minute cache protects the hot path — ``label_narrative`` runs
    under ``Semaphore(10)`` per article, so an uncached DB round-trip here
    multiplies into dozens on RSS-heavy days.
    """
    global _cached_anchor, _cached_at_monotonic

    now = time.monotonic()
    with _cache_lock:
        if _cached_anchor is not None and (now - _cached_at_monotonic) < ANCHOR_CACHE_TTL_SECONDS:
            return _cached_anchor

    from shared.neon import get_portfolio_holdings, get_swing_watchlist

    watchlist, holdings = await asyncio.gather(get_swing_watchlist(), get_portfolio_holdings())
    anchor = build_anchor_tickers(watchlist, holdings)

    with _cache_lock:
        _cached_anchor = anchor
        _cached_at_monotonic = time.monotonic()
        _cached_prompt_header = None  # invalidate rendered header too
    return anchor


def render_anchor_for_prompt(anchor: list[str]) -> str:
    """Render the anchor list into a single injection block for LLM prompts.

    Paired with the hint map (shared.ticker_extract.COMPANY_TICKERS) when the
    caller also wants brand-name anchoring.
    """
    from .vn_universe import VN_INDEX_PLACEHOLDER

    joined = ", ".join(anchor)
    return (
        "VN TICKER ANCHOR — output only VN-listed tickers. These are the most "
        "commonly referenced in Vietnamese financial news; other legitimate "
        "HOSE/HNX/UPCoM codes are allowed but non-VN codes (US, HK, etc.) are "
        "not. If a macro/geopolitical event affects the Vietnamese market as a "
        f"whole, use the placeholder {VN_INDEX_PLACEHOLDER} — do not invent "
        "ticker symbols.\n"
        f"Anchor ({len(anchor)}): {joined}"
    )


def render_brand_hint_map(extra: dict[str, str] | None = None) -> str:
    """Brand→ticker rows derived from ``shared.ticker_extract.COMPANY_TICKERS``.

    ``extra`` supplies LLM-only aliases (e.g. "FPT Telecom / FPT Play" → FOX)
    that don't belong in the regex-matcher's mapping.
    """
    from .ticker_extract import COMPANY_TICKERS

    combined = {**COMPANY_TICKERS, **(extra or {})}
    return "\n".join(f"- {name.title()} = {ticker}" for name, ticker in combined.items())


async def prime_and_render_vn_prompt_header(
    extra_hints: dict[str, str] | None = None,
) -> str:
    """One-call primer + renderer for every VN-ticker-aware agent prompt.

    Populates the ``vn_universe`` cache and the anchor cache (both 5 min
    TTL, so after the first hit the call is effectively free) then returns
    the rendered ``anchor + hint map`` prompt block the three news agents
    all prepend to their user prompt. Runs the two primer fetches
    concurrently via ``asyncio.gather``.
    """
    global _cached_prompt_header

    with _cache_lock:
        if _cached_prompt_header is not None and extra_hints is None:
            fresh = (time.monotonic() - _cached_at_monotonic) < ANCHOR_CACHE_TTL_SECONDS
            if fresh:
                return _cached_prompt_header

    from .vn_universe import load_vn_universe_async

    _, anchor = await asyncio.gather(load_vn_universe_async(), build_anchor_tickers_async())
    anchor_block = render_anchor_for_prompt(anchor)
    hint_map = render_brand_hint_map(extra_hints)
    header = f"{anchor_block}\n\nBRAND → TICKER HINT MAP:\n{hint_map}"

    if extra_hints is None:
        with _cache_lock:
            _cached_prompt_header = header
    return header


def reset_anchor_cache() -> None:
    """Reset the anchor cache — test-only hook."""
    global _cached_anchor, _cached_prompt_header, _cached_at_monotonic
    with _cache_lock:
        _cached_anchor = None
        _cached_prompt_header = None
        _cached_at_monotonic = 0.0
