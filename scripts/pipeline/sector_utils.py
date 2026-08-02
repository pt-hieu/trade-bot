"""Sector splitting and merging utilities for parallel execution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.rules.catalyst_override import CatalystBoost

logger = logging.getLogger(__name__)


def log_catalyst_boosted_outside_watchlist(
    sectors: dict[str, list[str]],
    catalyst_boosted: dict[str, CatalystBoost] | None,
) -> dict[str, list[str]]:
    """Observability-only scope-gate for outside-watchlist boosted tickers.

    Scope-gate (plan distributed-snuggling-brooks, Gap 1): only
    watchlist-resident boosted tickers are in scope. Tickers already in
    some sector bucket flow to the sector agent unchanged — no-op. For
    boosted tickers absent from every sector bucket, we emit one INFO
    log (so "catalyst active but never reached picks" is diagnosable in
    real time) and return sectors unchanged. Future work: resolve outside-
    watchlist tickers to canonical sectors via company_profiles.
    """
    if not catalyst_boosted:
        return sectors

    known_tickers: set[str] = set()
    for tickers in sectors.values():
        known_tickers.update(t.upper() for t in tickers)

    outside = [ticker for ticker in catalyst_boosted if ticker.upper() not in known_tickers]

    if outside:
        logger.info(
            "catalyst_boosted_outside_watchlist: %d boosted tickers have no "
            "sector assignment — deferred (out of scope this pipeline): %s",
            len(outside),
            sorted(outside),
        )
    return sectors


def split_sectors(sectors: dict, max_per_run: int = 5) -> dict:
    """Split sectors with >max_per_run tickers into named chunks.

    Example: banking (8) → banking_1 (5) + banking_2 (3).
    Callers must merge results back under the original name.
    """
    result = {}
    for name, tickers in sectors.items():
        if len(tickers) <= max_per_run:
            result[name] = tickers
        else:
            chunks = [tickers[i : i + max_per_run] for i in range(0, len(tickers), max_per_run)]
            for idx, chunk in enumerate(chunks, start=1):
                result[f"{name}_{idx}"] = chunk
    return result


def merge_split_sector_results(
    results_dict: dict,
    original_sectors: dict,
    split_sectors_map: dict,
) -> dict:
    """Merge chunked sector results back under original sector names.

    For sectors that were not split, returns value as-is. For split
    sectors, concatenates text and combines signals from the chunks that
    succeeded; if EVERY chunk raised, returns the first Exception so the
    Phase 2 health gate's `isinstance(value, Exception)` branch counts
    the sector as failed (a success-shaped empty dict would not).
    """
    merged = {}
    for name in original_sectors:
        if name in split_sectors_map:
            # Not split — use directly
            merged[name] = results_dict.get(f"sector_{name}")
            continue

        # Split — walk chunks, preserve per-chunk success/failure signal.
        chunk_keys = sorted(k for k in split_sectors_map if k.startswith(f"{name}_"))
        texts: list[str] = []
        signals: list[dict] = []
        beliefs: list[dict] = []
        any_success = False
        first_exception: Exception | None = None
        saw_any_value = False
        for chunk_key in chunk_keys:
            value = results_dict.get(f"sector_{chunk_key}")
            if value is None:
                continue
            saw_any_value = True
            if isinstance(value, dict):
                any_success = True
                texts.append(value.get("text", ""))
                signals.extend(value.get("signals", []))
                beliefs.extend(value.get("beliefs", []))
            elif isinstance(value, Exception):
                if first_exception is None:
                    first_exception = value
                texts.append(f"## {chunk_key}\nAnalysis failed: {value}")

        if any_success:
            merged[name] = {
                "text": "\n\n".join(texts),
                "signals": signals,
                "beliefs": beliefs,
            }
        elif first_exception is not None:
            # Every chunk errored — surface the Exception so health gate counts
            # this sector as failed (see RuntimeError in run_phase2_parallel).
            merged[name] = first_exception
        elif saw_any_value:
            # Chunks returned non-dict/non-exception values (legacy strings).
            # Treat as soft-missing so health gate counts failure.
            merged[name] = None
        else:
            merged[name] = None
    return merged
