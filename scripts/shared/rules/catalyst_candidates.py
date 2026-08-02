"""Bounded catalyst candidate selector — pure deterministic Python.

Core of DEF-005. Converts raw changed-catalyst rows into a dedup'd list of
ticker × catalyst pairs that a downstream pick generator may attempt to
promote to BUY. The selector enforces two hard bounds:

1. **Impact/confidence**: only POSITIVE catalysts with HIGH or MEDIUM
   confidence produce candidates. NEGATIVE and LOW are fail-closed — they
   never become BUYs regardless of how many tickers they name.
2. **Ticker universe**: a candidate ticker MUST already be in our holdings
   or active watchlists (swing ∪ longterm). The selector CANNOT widen the
   traded universe — a HIGH/POSITIVE catalyst naming an out-of-universe
   ticker produces zero candidates.

Deduplication: when the same ticker appears under multiple catalysts, the
(impact_rank, confidence_rank) winner is kept. POSITIVE > NEGATIVE > NEUTRAL
and HIGH > MEDIUM > LOW. Ties fall through to first-seen order.
"""

from __future__ import annotations

from typing import TypedDict

# Impact/confidence ranking. Higher integer = stronger candidate.
_IMPACT_RANK: dict[str, int] = {"POSITIVE": 2, "NEUTRAL": 1, "NEGATIVE": 0}
_CONFIDENCE_RANK: dict[str, int] = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}

# Only these (impact, confidence) pairs produce BUY candidates. Negative
# and LOW catalysts fail closed — no BUY promotion.
_ELIGIBLE_IMPACTS: frozenset[str] = frozenset({"POSITIVE"})
_ELIGIBLE_CONFIDENCES: frozenset[str] = frozenset({"HIGH", "MEDIUM"})


class CatalystCandidate(TypedDict):
    """A ticker × catalyst pair eligible for BUY promotion."""

    ticker: str
    catalyst_key: str
    catalyst_event: str
    impact: str
    confidence: str


def select_catalyst_candidates(
    changed_catalysts: list[dict],
    holdings_tickers: set[str],
    watchlist_tickers: set[str],
) -> list[CatalystCandidate]:
    """Pick ticker × catalyst pairs that may be promoted to BUY.

    Args:
        changed_catalysts: Raw rows from the catalyst spike detector. Each
            dict is expected to carry ``impact``, ``confidence``,
            ``affected_tickers`` (list[str]), ``catalyst_key`` (or ``id``),
            and ``event``.
        holdings_tickers: Upper-cased ticker set from ``portfolio_holdings``.
        watchlist_tickers: Upper-cased ticker set from swing ∪ longterm.

    Returns:
        One ``CatalystCandidate`` per ticker — the highest-ranked catalyst
        attached to that ticker wins on dedup. Order: deterministic,
        following the input order after dedup.
    """
    universe = {ticker.upper() for ticker in (holdings_tickers | watchlist_tickers)}
    if not universe or not changed_catalysts:
        return []

    # Track best candidate per ticker for dedup.
    best: dict[str, tuple[int, int, CatalystCandidate]] = {}

    for catalyst in changed_catalysts:
        impact = (catalyst.get("impact") or "").upper()
        confidence = (catalyst.get("confidence") or "").upper()
        if impact not in _ELIGIBLE_IMPACTS:
            continue
        if confidence not in _ELIGIBLE_CONFIDENCES:
            continue

        catalyst_key = catalyst.get("catalyst_key") or catalyst.get("id") or ""
        event = catalyst.get("event") or ""
        affected = catalyst.get("affected_tickers") or catalyst.get("affected") or []

        impact_rank = _IMPACT_RANK.get(impact, 0)
        confidence_rank = _CONFIDENCE_RANK.get(confidence, 0)

        for raw_ticker in affected:
            ticker = (raw_ticker or "").upper()
            if not ticker or ticker not in universe:
                continue

            current = best.get(ticker)
            if current and (current[0], current[1]) >= (impact_rank, confidence_rank):
                continue

            best[ticker] = (
                impact_rank,
                confidence_rank,
                CatalystCandidate(
                    ticker=ticker,
                    catalyst_key=catalyst_key,
                    catalyst_event=event,
                    impact=impact,
                    confidence=confidence,
                ),
            )

    return [candidate for _, _, candidate in best.values()]


__all__ = ["CatalystCandidate", "select_catalyst_candidates"]
