"""Belief-fallback rule: promote BULLISH aggregator beliefs into pick candidates.

Pure deterministic Python, no async / DB / LLM — matches the sibling
`catalyst_override` pattern in this package. Used when sector agents
partially fail so a degraded morning can still emit picks.
"""

from __future__ import annotations


def derive_belief_boosted_tickers(
    sector_beliefs: list[dict] | None,
    sector_signals: list[dict],
    exclude_tickers: list[str],
    max_picks: int,
) -> set[str]:
    """BULLISH aggregator-belief tickers not already emitting sector BUY.

    Headroom capped at ``max_picks - existing_buy_count`` so a 10-BULLISH
    morning doesn't flood the picks layer. Returns upper-case tickers.
    """
    existing_buy_tickers = {
        (s.get("ticker") or "").upper()
        for s in sector_signals
        if (s.get("signal") or "").upper() == "BUY"
    }
    excluded = {t.upper() for t in exclude_tickers}
    headroom = max(0, max_picks - len(existing_buy_tickers))
    if headroom == 0:
        return set()
    candidates: list[str] = []
    for belief in sector_beliefs or []:
        ticker = (belief.get("ticker") or "").upper()
        direction = (belief.get("direction") or "").upper()
        if (
            ticker
            and direction == "BULLISH"
            and ticker not in existing_buy_tickers
            and ticker not in excluded
        ):
            candidates.append(ticker)
    return set(candidates[:headroom])
