"""Shared rate-limit semaphore + sector output collector for Phase 1/Phase 2.

The ``_API_SEMAPHORE`` is the SINGLE Semaphore instance shared by both
``phase1.py`` and ``phase2.py`` (FIX 6 invariant — see
``tests/unit/test_phase_parallel_singleton.py``). Re-binding the
semaphore in any submodule breaks the rate-limit guarantee silently.
"""

from __future__ import annotations

import asyncio
from typing import Any

from shared.errors import report_caught

# Rate limiting semaphore (max concurrent API calls). Lives at this
# module's scope so phase1 + phase2 + the package __init__ all reference
# the same Semaphore object — see tests/unit/test_phase_parallel_singleton.py.
_API_SEMAPHORE = asyncio.Semaphore(4)


async def _run_with_semaphore(coro, name: str) -> tuple[str, Any]:
    """Run a coroutine with rate limiting and error handling.

    Returns:
        Tuple of (name, result) where result may be an Exception.
    """
    async with _API_SEMAPHORE:
        try:
            result = await coro
            return (name, result)
        except Exception as e:
            report_caught(name, e)
            return (name, e)


def _collect_sector_outputs(
    sectors: dict,
    merged: dict,
    *,
    verbose: bool = True,
) -> tuple[list[str], list[dict], list[dict], int]:
    """Parse merged sector results into (texts, signals, beliefs, failed_count).

    Extracted so Phase 2a checkpoint (pre-positions) and Phase 2 final
    result (post-positions) share one derivation — `Single derivation path`
    rule from CLAUDE.md.
    """
    sector_results: list[str] = []
    sector_signals: list[dict] = []
    sector_beliefs: list[dict] = []
    failed_sector_count = 0
    for name in sectors:
        value = merged.get(name)
        if isinstance(value, Exception):
            sector_results.append(f"## {name}\nAnalysis failed: {value}")
            failed_sector_count += 1
            if verbose:
                print(f"  [sector_{name}] FAILED", flush=True)
        elif isinstance(value, dict):
            sector_results.append(value.get("text", f"## {name}\nNo text"))
            sector_signals.extend(value.get("signals", []))
            sector_beliefs.extend(value.get("beliefs", []))
            if verbose:
                buy_count = sum(1 for s in value.get("signals", []) if s.get("signal") == "BUY")
                input_ticker_set = {t.upper() for t in sectors.get(name, [])}
                output_ticker_set = {
                    (s.get("ticker") or "").upper()
                    for s in value.get("signals", [])
                    if s.get("ticker")
                }
                phase2_dropped = sorted(input_ticker_set - output_ticker_set)
                if phase2_dropped:
                    print(
                        f"  [sector_{name}] DROPPED tickers: {phase2_dropped} "
                        f"(input={sorted(input_ticker_set)}, "
                        f"output={sorted(output_ticker_set)})",
                        flush=True,
                    )
                print(f"  [sector_{name}] OK ({buy_count} BUY signals)", flush=True)
        elif value is None:
            sector_results.append(f"## {name}\nNo analysis produced")
            failed_sector_count += 1
            if verbose:
                print(f"  [sector_{name}] MISSING", flush=True)
        else:
            sector_results.append(str(value))
            if verbose:
                print(f"  [sector_{name}] OK (unstructured)", flush=True)
    return sector_results, sector_signals, sector_beliefs, failed_sector_count
