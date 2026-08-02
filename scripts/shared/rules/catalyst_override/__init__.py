"""Catalyst-aware context boosting — pure deterministic Python.

No async, no DB, no LLM. Identifies tickers boosted by active positive
catalysts for prioritization in entry strategist context and for the
MEAN_REVERSION → MOMENTUM promotion in strategy_classifier.

Also hosts the per-ticker geo-exposure aggregator (`classify_geo_label`)
that replaces the split-brain of `context_blocks_macro.classify_geo_exposure`
+ the catalyst-boost path reading them separately. Unified classification
so a stacked-positive-catalyst ticker during a shock lands on `GEO_MIXED`
instead of silently flipping to `GEO_VICTIM` inside the sector LLM.

Module layout (post-modularisation, SWI-212):
  * ``types.py`` — TypedDicts + shared enums + STACKED_POSITIVE_MIN_CATALYSTS.
  * ``boosting.py`` — get_catalyst_boosted_tickers + lifecycle helpers.
  * ``blanket.py`` — get_macro_blanket_boosts (VN-INDEX fan-out).
  * ``validators.py`` — has_*/count_* predicates for Rule 5a + streak relaxation.
  * ``geolabel.py`` — classify_geo_label aggregator.
  * ``__init__.py`` — public API: format_catalyst_boost_context + re-exports.
"""

from __future__ import annotations

from .blanket import get_macro_blanket_boosts
from .boosting import (
    _BOOST_LIFECYCLES,
    _BOOST_LOW_CONFIDENCE_LIFECYCLES,
    _BOOST_LOW_MIN_ARTICLES,
    _RR_FLOOR_ADJUSTMENT_BY_CONFIDENCE,
    get_catalyst_boosted_tickers,
)
from .geolabel import _has_stacked_positive_catalysts, classify_geo_label
from .types import (
    STACKED_POSITIVE_MIN_CATALYSTS,
    BoostLifecycle,
    CatalystBoost,
    CatalystInput,
    CatalystType,
    GeoLabel,
)
from .validators import (
    count_high_positive_per_ticker,
    has_high_positive_macro_blanket_catalyst,
    has_high_positive_per_ticker_catalyst,
)


def format_catalyst_boost_context(boosted: dict[str, CatalystBoost]) -> str:
    """Format boosted tickers as a context block for entry strategist.

    Returns empty string if no boosted tickers.
    """
    if not boosted:
        return ""

    by_catalyst: dict[str, list[str]] = {}
    catalyst_reasons: dict[str, str] = {}
    for ticker, boost in boosted.items():
        key = boost["catalyst_key"]
        if key not in by_catalyst:
            by_catalyst[key] = []
            catalyst_reasons[key] = boost["reason"]
        by_catalyst[key].append(ticker)

    lines = ["## CATALYST-BOOSTED TICKERS (prioritize these for entries)"]
    for catalyst_key, tickers in by_catalyst.items():
        reason = catalyst_reasons[catalyst_key]
        ticker_str = ", ".join(sorted(tickers)[:10])
        remaining = len(tickers) - 10
        if remaining > 0:
            ticker_str += f" +{remaining} more"
        lines.append(f"- {ticker_str}: {reason}")

    return "\n".join(lines)


__all__ = [
    "STACKED_POSITIVE_MIN_CATALYSTS",
    "BoostLifecycle",
    "CatalystBoost",
    "CatalystInput",
    "CatalystType",
    "GeoLabel",
    "_BOOST_LIFECYCLES",
    "_BOOST_LOW_CONFIDENCE_LIFECYCLES",
    "_BOOST_LOW_MIN_ARTICLES",
    "_RR_FLOOR_ADJUSTMENT_BY_CONFIDENCE",
    "_has_stacked_positive_catalysts",
    "classify_geo_label",
    "count_high_positive_per_ticker",
    "format_catalyst_boost_context",
    "get_catalyst_boosted_tickers",
    "get_macro_blanket_boosts",
    "has_high_positive_macro_blanket_catalyst",
    "has_high_positive_per_ticker_catalyst",
]
