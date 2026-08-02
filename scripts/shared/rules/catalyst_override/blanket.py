"""Macro/geopolitical/commodity catalyst fan-out across the candidate universe."""

from __future__ import annotations

from collections.abc import Sequence

from ..catalyst_news import classify_macro_catalyst_scope
from .boosting import _upsert_boost
from .types import CatalystBoost, CatalystInput

# Macro-blanket fan-out: half the magnitude of the standard HIGH/POSITIVE
# boost (0.5) because the transmission from a market-wide catalyst to any
# individual ticker is inferred, not declared.
_MACRO_BLANKET_RR_ADJUSTMENT: dict[str, float] = {
    "HIGH": 0.25,
    "MEDIUM": 0.125,
}


def get_macro_blanket_boosts(
    catalysts: Sequence[CatalystInput],
    candidate_universe: Sequence[str],
    *,
    positive_only_fan_out: bool = True,
) -> dict[str, CatalystBoost]:
    """Fan macro/geopolitical/commodity catalysts onto the candidate universe.

    Returns a separate dict from :func:`get_catalyst_boosted_tickers` so
    callers merge per-ticker first (explicit wins) and consult the macro
    fan-out as a secondary boost source. Each entry carries
    ``phase_lifecycle="MACRO_BLANKET"`` so ``_lifecycle_priority`` returns 0
    and the entry can never upgrade an explicit per-ticker boost when the
    two dicts are merged via ``_upsert_boost``.

    Args:
        catalysts: Full active catalyst list (typed).
        candidate_universe: Tickers eligible for fan-out — pass the swing
            watchlist ∪ holdings so negative-sided fan-out (blocked below)
            doesn't leak into the gate.
        positive_only_fan_out: When True (default), NEGATIVE macro
            catalysts are never fanned out. ``entry_gates.py`` already
            clamps ``catalyst_rr_adjustment`` via ``max(0.0, …)`` but
            making the fan-out itself positive-only prevents the
            "apparent symmetry" drift the challenger flagged (F-comment
            in AUDIT-2026-04-24-001 plan).

    Returns:
        ``{ticker: CatalystBoost}`` with ``phase_lifecycle='MACRO_BLANKET'``.
    """
    fanned: dict[str, CatalystBoost] = {}
    if not candidate_universe:
        return fanned
    universe_list = list(dict.fromkeys(candidate_universe))

    for catalyst in catalysts:
        if positive_only_fan_out and catalyst["impact"] != "POSITIVE":
            continue
        confidence = catalyst["confidence"]
        if confidence not in _MACRO_BLANKET_RR_ADJUSTMENT:
            # LOW-confidence macro catalysts never fan out — they add noise
            # without the corroboration signal to justify relaxing gates.
            continue
        scope = classify_macro_catalyst_scope(
            {
                "affected_tickers": catalyst["affected_tickers"],
                "catalyst_type": catalyst.get("catalyst_type"),
            }
        )
        if scope != "macro_blanket":
            continue
        adjustment = _MACRO_BLANKET_RR_ADJUSTMENT[confidence]
        reason = f"{catalyst['event'][:60]} — macro blanket fan-out ({confidence})"
        candidate = CatalystBoost(
            ticker="",
            catalyst_key=catalyst["catalyst_key"],
            catalyst_event=catalyst["event"],
            phase_lifecycle="MACRO_BLANKET",
            phase_name="",
            reason=reason,
            rr_floor_adjustment=adjustment,
        )
        for ticker in universe_list:
            _upsert_boost(fanned, ticker, candidate)
    return fanned
