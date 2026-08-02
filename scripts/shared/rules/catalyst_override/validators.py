"""Predicates / counters consumed by recommendation_gate Rule 5a + sibling streak relaxation."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from shared.vn_universe import VN_INDEX_PLACEHOLDER

from ..catalyst_news import classify_macro_catalyst_scope
from .types import _MIXED_ELIGIBLE_CONFIDENCE, CatalystInput


def has_high_positive_macro_blanket_catalyst(
    catalysts: Sequence[CatalystInput] | None,
) -> bool:
    """True when at least one HIGH/POSITIVE macro-blanket catalyst is active.

    Consumed by ``compose_recommendation_gate`` / ``_streak_relaxation`` so
    a 3+ day zero-BUY streak co-occurring with a HIGH macro tailwind flips
    ``belief_flattening``/``regime_gated`` surface profiles to ``rr_floor``
    (AUDIT-2026-04-24-001 / ISSUE-2026-04-24-002).
    """
    for _ in _iter_high_positive_catalysts(catalysts, scope="macro_blanket"):
        return True
    return False


def count_high_positive_per_ticker(
    catalysts: Sequence[CatalystInput] | None,
    candidate_tickers: Iterable[str],
) -> dict[str, int]:
    """Count HIGH/MEDIUM POSITIVE catalysts per ticker for stacked-shock relief.

    L2 (2026-04-27): consumed by ``check_candidate_gate``'s
    ``stacked_shock_relief`` flag. A ticker qualifies for the per-candidate
    R:R floor cap (3.0) when it is shock-affected AND its count here meets
    ``STACKED_POSITIVE_MIN_CATALYSTS`` (=2). Counts only POSITIVE catalysts
    with HIGH or MEDIUM confidence; LOW and NEGATIVE never contribute.

    Returns a ``{ticker: count}`` mapping. Tickers with zero qualifying
    catalysts are absent. Tickers outside ``candidate_tickers`` are
    excluded entirely so the caller can use ``count.get(ticker, 0) >= N``
    safely.
    """
    universe = {str(t).upper() for t in candidate_tickers if t}
    counts: dict[str, int] = {}
    if not universe or not catalysts:
        return counts
    for catalyst in catalysts:
        if catalyst.get("impact") != "POSITIVE":
            continue
        if catalyst.get("confidence") not in _MIXED_ELIGIBLE_CONFIDENCE:
            continue
        for raw_ticker in catalyst.get("affected_tickers") or []:
            ticker = str(raw_ticker).upper()
            if ticker == VN_INDEX_PLACEHOLDER:
                continue
            if ticker not in universe:
                continue
            counts[ticker] = counts.get(ticker, 0) + 1
    return counts


def has_high_positive_per_ticker_catalyst(
    catalysts: Sequence[CatalystInput] | None,
    candidate_tickers: Iterable[str],
) -> bool:
    """True when a HIGH/POSITIVE per-ticker catalyst overlaps ``candidate_tickers``.

    Per-ticker counterpart to :func:`has_high_positive_macro_blanket_catalyst`.
    Used by ``compose_recommendation_gate`` Rule 5a so the stressed-regime
    floor can relax when a concrete ticker in today's universe (watchlist
    ∪ holdings) carries a HIGH positive catalyst. Macro-blanket rows
    (VN-INDEX placeholder only) are handled via the macro path and skipped
    here to avoid double-counting.
    """
    universe = {str(t).upper() for t in candidate_tickers if t}
    if not universe:
        return False
    for catalyst in _iter_high_positive_catalysts(catalysts, scope="per_ticker"):
        tickers = {
            str(ticker).upper()
            for ticker in (catalyst.get("affected_tickers") or [])
            if ticker and str(ticker).upper() != VN_INDEX_PLACEHOLDER
        }
        if tickers & universe:
            return True
    return False


def _iter_high_positive_catalysts(
    catalysts: Sequence[CatalystInput] | None,
    *,
    scope: Literal["macro_blanket", "per_ticker"],
) -> Iterable[CatalystInput]:
    """Yield HIGH/POSITIVE catalysts matching ``scope``."""
    for catalyst in catalysts or []:
        if catalyst.get("impact") != "POSITIVE":
            continue
        if catalyst.get("confidence") != "HIGH":
            continue
        catalyst_scope = classify_macro_catalyst_scope(
            {
                "affected_tickers": catalyst.get("affected_tickers") or [],
                "catalyst_type": catalyst.get("catalyst_type"),
            }
        )
        if catalyst_scope != scope:
            continue
        yield catalyst
